# generator.py
"""Group generation module for balanced participant distribution."""

import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass
class LimitConstraint:
    """Represents a limit constraint with priority.
    
    Attributes:
        members: Set of participant names that have a restriction
        priority: Lower number = higher priority (2-member limits have priority 0 by default)
        max_together: Maximum number of these members allowed in the same group.
                     If None, calculated as max(1, num_groups - 1) when applied,
                     meaning ideally only 1 per group, but relaxed if members > groups.
    """
    members: frozenset
    priority: int = 0
    max_together: Optional[int] = None
    
    @classmethod
    def from_pair(cls, person1: str, person2: str, priority: int = 0) -> 'LimitConstraint':
        """Create a constraint from two people."""
        return cls(members=frozenset([person1, person2]), priority=priority, max_together=1)
    
    @classmethod
    def from_group(cls, members: list[str], priority: int = 1, max_together: Optional[int] = None) -> 'LimitConstraint':
        """Create a constraint from multiple people (3+).
        
        Args:
            members: List of member names
            priority: Priority level (lower = higher priority)
            max_together: Maximum members allowed together. If None, will be calculated
                         based on number of groups at application time.
        """
        if len(members) < 2:
            raise ValueError("A limit constraint must have at least 2 members")
        return cls(members=frozenset(members), priority=priority, max_together=max_together)
    
    def get_max_together(self, num_groups: int) -> int:
        """Calculate maximum members allowed together based on group count.
        
        If max_together is set, use it. Otherwise, calculate based on pigeonhole principle:
        - If members <= num_groups: ideally 1 per group (max_together=1)
        - If members > num_groups: must allow some grouping, so ceil(members/num_groups)
        """
        if self.max_together is not None:
            return self.max_together
        
        # Calculate ideal distribution
        # If we have N members and G groups, at least one group must have ceil(N/G) members
        import math
        return max(1, math.ceil(len(self.members) / num_groups))
    
    def is_violated_by(self, group_set: set[str], num_groups: int) -> bool:
        """Check if this constraint is violated by a group.
        
        A constraint is violated if more than the allowed number of members are in the group.
        The allowed number is calculated based on the total number of groups.
        """
        max_allowed = self.get_max_together(num_groups)
        members_in_group = len(self.members & group_set)
        return members_in_group > max_allowed


@dataclass
class GroupingResult:
    """Result of group generation attempt."""
    
    groups: list[list[str]]
    attempts: int
    status: str
    warnings: list[str]
    used_seed: int
    balance_metrics: dict = field(default_factory=dict)


def verify_groups(
    groups: list[list[str]],
    limits: Union[dict[str, list[str]], list[LimitConstraint]],
    roles: dict[str, str],
    genders: dict[str, str],
    strict_r: bool = True,
    strict_g: bool = True,
) -> bool:
    """Verify that generated groups meet all constraints.
    
    Args:
        groups: List of groups, each containing participant names
        limits: Either a dictionary mapping participants to lists of people they can't be grouped with,
                or a list of LimitConstraint objects for multi-member constraints with priority
        roles: Dictionary mapping participants to their roles
        genders: Dictionary mapping participants to their genders
        strict_r: Whether to enforce strict role balance
        strict_g: Whether to enforce strict gender balance
        
    Returns:
        True if all constraints are satisfied, False otherwise
    """
    # Check for duplicates
    flat = [person for group in groups for person in group]
    if len(flat) != len(set(flat)):
        return False
    
    # Check group size balance (difference <= 1)
    if max(len(g) for g in groups) - min(len(g) for g in groups) > 1:
        return False
    
    # Build conflict map from legacy format or use LimitConstraints
    conflicts = defaultdict(set)
    limit_constraints = []
    
    if isinstance(limits, list):
        # New format: list of LimitConstraint objects
        limit_constraints = limits
        # Also build pairwise conflicts for 2-member constraints
        for constraint in limit_constraints:
            if len(constraint.members) == 2:
                members_list = list(constraint.members)
                conflicts[members_list[0]].add(members_list[1])
                conflicts[members_list[1]].add(members_list[0])
    else:
        # Legacy format: dict[str, list[str]]
        for person, others in limits.items():
            for other in others:
                conflicts[person].add(other)
    
    # Check no pairwise conflicts within groups
    for group in groups:
        group_set = set(group)
        for person in group:
            if conflicts[person] & group_set:
                return False
    
    # Check multi-member constraints (members should be distributed across groups)
    num_groups = len(groups)
    for constraint in limit_constraints:
        if len(constraint.members) >= 3:
            max_allowed = constraint.get_max_together(num_groups)
            for group in groups:
                group_set = set(group)
                members_in_group = len(constraint.members & group_set)
                if members_in_group > max_allowed:
                    return False
    
    # Check role balance
    if strict_r:
        role_totals = defaultdict(int)
        for role in roles.values():
            role_totals[role] += 1
        
        role_targets = {
            role: [base + (1 if i < remainder else 0) for i in range(num_groups)]
            for role, count in role_totals.items()
            for base, remainder in [divmod(count, num_groups)]
        }
        
        for i, group in enumerate(groups):
            group_role_counts = defaultdict(int)
            for person in group:
                group_role_counts[roles[person]] += 1
            
            for role in role_targets:
                if group_role_counts.get(role, 0) != role_targets[role][i]:
                    return False
    
    # Check gender balance
    if strict_g:
        gender_totals = defaultdict(int)
        for gender in genders.values():
            gender_totals[gender] += 1
        
        gender_targets = {
            gender: [base + (1 if i < remainder else 0) for i in range(num_groups)]
            for gender, count in gender_totals.items()
            for base, remainder in [divmod(count, num_groups)]
        }
        
        for i, group in enumerate(groups):
            group_gender_counts = defaultdict(int)
            for person in group:
                group_gender_counts[genders[person]] += 1
            
            for gender in gender_targets:
                if group_gender_counts.get(gender, 0) != gender_targets[gender][i]:
                    return False
    
    return True


def _run_attempt(seed: int, config: dict) -> Optional[GroupingResult]:
    """Run a single group generation attempt with given seed.
    
    Args:
        seed: Random seed for reproducibility
        config: Configuration dictionary containing all generation parameters
        
    Returns:
        GroupingResult if successful, None if failed
    """
    rng = random.Random(seed)
    all_people = config['all']
    roles = config['roles']
    genders = config['genders']
    conflicts = config['conflicts']
    limit_constraints = config.get('limit_constraints', [])
    size_targets = config['size_tgt']
    role_targets = config['role_tgt']
    gender_targets = config['gender_tgt']
    strict_r = config['strict_r']
    strict_g = config['strict_g']
    num_groups = config['g_num']
    
    # Sort by number of conflicts (most constrained first)
    pool = sorted(all_people, key=lambda p: len(conflicts[p]), reverse=True)
    rng.shuffle(pool)
    
    # Initialize groups and counters
    groups = [[] for _ in range(num_groups)]
    group_role_counts = [defaultdict(int) for _ in range(num_groups)]
    group_gender_counts = [defaultdict(int) for _ in range(num_groups)]
    warnings = []
    
    def check_multi_member_constraints(group_idx: int, person: str) -> bool:
        """Check if adding person to group would violate any multi-member constraint.
        
        Returns True if valid (no violation), False if violation.
        """
        group_set = set(groups[group_idx])
        group_set.add(person)
        for constraint in limit_constraints:
            if len(constraint.members) >= 3:
                max_allowed = constraint.get_max_together(num_groups)
                members_in_group = len(constraint.members & group_set)
                if members_in_group > max_allowed:
                    return False
        return True
    
    # Assign participants to groups
    for person in pool:
        role = roles[person]
        gender = genders[person]
        
        # Find valid groups
        valid_groups = [
            i for i in range(num_groups)
            if len(groups[i]) < size_targets[i]
            and (not strict_r or group_role_counts[i][role] < role_targets[role][i])
            and (not strict_g or group_gender_counts[i][gender] < gender_targets[gender][i])
            and not any(person in conflicts[member] for member in groups[i])
            and check_multi_member_constraints(i, person)
        ]
        
        # Relax constraints if needed
        if not valid_groups and (strict_r or strict_g):
            valid_groups = [
                i for i in range(num_groups)
                if len(groups[i]) < size_targets[i]
                and not any(person in conflicts[member] for member in groups[i])
                and check_multi_member_constraints(i, person)
            ]
            if valid_groups and not warnings:
                warnings.append("Баланс ролей/полов ослаблен.")
        
        if not valid_groups:
            return None
        
        # Assign to random valid group
        idx = rng.choice(valid_groups)
        groups[idx].append(person)
        group_role_counts[idx][role] += 1
        group_gender_counts[idx][gender] += 1
    
    # Local optimization: swap participants to improve balance
    def calculate_score():
        role_deviation = sum(
            sum(abs(group_role_counts[i][role] - role_targets[role][i]) for role in role_targets)
            for i in range(num_groups)
        )
        gender_deviation = sum(
            sum(abs(group_gender_counts[i][gender] - gender_targets[gender][i]) for gender in gender_targets)
            for i in range(num_groups)
        )
        return role_deviation + gender_deviation
    
    best_score = calculate_score()
    stagnation_counter = 0
    
    for _ in range(150):
        if stagnation_counter >= 25:
            break
        
        g1, g2 = rng.sample(range(num_groups), 2)
        if not groups[g1] or not groups[g2]:
            continue
        
        p1, p2 = rng.choice(groups[g1]), rng.choice(groups[g2])
        r1, r2 = roles[p1], roles[p2]
        gn1, gn2 = genders[p1], genders[p2]
        
        # Check conflict constraints after swap
        if any(p1 in conflicts[m] for m in groups[g2] if m != p2):
            continue
        if any(p2 in conflicts[m] for m in groups[g1] if m != p1):
            continue
        
        # Check multi-member constraints after swap
        def would_violate_multi_member(group_idx: int, person: str) -> bool:
            group_set = set(groups[group_idx])
            group_set.discard(p1 if group_idx == g1 else p2)
            group_set.add(person)
            for constraint in limit_constraints:
                if len(constraint.members) >= 3:
                    max_allowed = constraint.get_max_together(num_groups)
                    members_in_group = len(constraint.members & group_set)
                    if members_in_group > max_allowed:
                        return True
            return False
        
        if would_violate_multi_member(g2, p1):
            continue
        if would_violate_multi_member(g1, p2):
            continue
        
        # Check role/gender capacity constraints
        if strict_r and (group_role_counts[g2][r1] + 1 > role_targets[r1][g2] 
                         or group_role_counts[g1][r2] + 1 > role_targets[r2][g1]):
            continue
        if strict_g and (group_gender_counts[g2][gn1] + 1 > gender_targets[gn1][g2] 
                         or group_gender_counts[g1][gn2] + 1 > gender_targets[gn2][g1]):
            continue
        
        # Perform swap
        groups[g1].remove(p1)
        groups[g1].append(p2)
        groups[g2].remove(p2)
        groups[g2].append(p1)
        
        group_role_counts[g1][r1] -= 1
        group_role_counts[g1][r2] += 1
        group_role_counts[g2][r2] -= 1
        group_role_counts[g2][r1] += 1
        
        group_gender_counts[g1][gn1] -= 1
        group_gender_counts[g1][gn2] += 1
        group_gender_counts[g2][gn2] -= 1
        group_gender_counts[g2][gn1] += 1
        
        new_score = calculate_score()
        
        if new_score < best_score:
            best_score = new_score
            stagnation_counter = 0
        elif new_score == best_score:
            if rng.random() < 0.1:
                rng.shuffle(groups)
            else:
                stagnation_counter += 1
        else:
            # Revert swap
            groups[g1].remove(p2)
            groups[g1].append(p1)
            groups[g2].remove(p1)
            groups[g2].append(p2)
            
            group_role_counts[g1][r1] += 1
            group_role_counts[g1][r2] -= 1
            group_role_counts[g2][r2] += 1
            group_role_counts[g2][r1] -= 1
            
            group_gender_counts[g1][gn1] += 1
            group_gender_counts[g1][gn2] -= 1
            group_gender_counts[g2][gn2] += 1
            group_gender_counts[g2][gn1] -= 1
            
            stagnation_counter += 1
    
    # Calculate balance metrics
    balance_metrics = {
        "size_diff": max(len(g) for g in groups) - min(len(g) for g in groups),
        "role_dev": {
            role: [group_role_counts[i][role] - role_targets[role][i] for i in range(num_groups)]
            for role in role_targets
        },
        "gender_dev": {
            gender: [group_gender_counts[i][gender] - gender_targets[gender][i] for i in range(num_groups)]
            for gender in gender_targets
        }
    }
    
    return GroupingResult(
        groups=groups,
        attempts=1,
        status="success",
        warnings=warnings,
        used_seed=seed,
        balance_metrics=balance_metrics
    )


def generate_groups(
    n: int,
    all_people: list[str],
    genders: dict[str, str],
    newbies: Optional[list[str]] = None,
    experts: Optional[list[str]] = None,
    roles: Optional[dict[str, str]] = None,
    limits: Optional[Union[dict[str, list[str]], list[LimitConstraint]]] = None,
    seed: Optional[int] = None,
    strict_r: bool = True,
    strict_g: bool = True,
    max_attempts: int = 500,
    workers: int = 0,
) -> GroupingResult:
    """Generate balanced groups from participants.
    
    Args:
        n: Number of groups to create
        all_people: List of all participant names
        genders: Dictionary mapping participants to genders ('M' or 'F')
        newbies: Optional list of newbie participants
        experts: Optional list of expert/VPI participants
        roles: Optional dictionary mapping participants to roles
        limits: Either a dictionary mapping participants to lists of people they can't be with,
                or a list of LimitConstraint objects for multi-member constraints with priority.
                By default, 2-member constraints have priority 0 (higher), and 3+ member 
                constraints have priority 1 (lower).
        seed: Optional random seed for reproducibility
        strict_r: Whether to enforce strict role balance
        strict_g: Whether to enforce strict gender balance
        max_attempts: Maximum number of generation attempts
        workers: Number of parallel workers (0 for single-threaded)
        
    Returns:
        GroupingResult containing the generated groups and metadata
        
    Raises:
        ValueError: If input validation fails
        RuntimeError: If generation fails after max_attempts
    """
    used_seed = seed if seed is not None else random.randint(0, 2**32 - 1)
    all_set = set(all_people)
    
    # Validate inputs
    if len(all_set) != len(all_people):
        raise ValueError("Дубликаты в списке участников.")
    
    if len(all_people) < n:
        raise ValueError("Участников меньше, чем групп.")
    
    if set(genders.keys()) != all_set:
        raise ValueError("genders не покрывает всех участников.")
    
    # Build roles dictionary
    if roles is None:
        if newbies and experts and set(newbies) & set(experts):
            raise ValueError("newbies и experts пересекаются.")
        
        roles = {p: 'newbie' for p in (newbies or [])}
        roles.update({p: 'expert' for p in (experts or [])})
        for p in all_people:
            roles.setdefault(p, 'regular')
    
    if set(roles.keys()) - all_set:
        raise ValueError("Неизвестные имена в roles.")
    
    # Process limits into unified format
    limit_constraints: list[LimitConstraint] = []
    conflicts = defaultdict(set)
    
    if limits is None:
        limits_input: Union[dict, list] = {}
    elif isinstance(limits, list):
        # New format: list of LimitConstraint objects
        limits_input = limits
        limit_constraints = limits
        # Build pairwise conflicts from 2-member constraints
        for constraint in limit_constraints:
            if not all(member in all_set for member in constraint.members):
                missing = [m for m in constraint.members if m not in all_set]
                raise ValueError(
                    f"Имя '{missing[0]}' отсутствует в списке участников."
                )
            # For 2-member constraints, add to pairwise conflicts
            if len(constraint.members) == 2:
                members_list = list(constraint.members)
                conflicts[members_list[0]].add(members_list[1])
                conflicts[members_list[1]].add(members_list[0])
    else:
        # Legacy format: dict[str, list[str]]
        limits_input = limits
        for person, others in limits.items():
            if person not in all_set or not all(other in all_set for other in others):
                raise ValueError(
                    f"Имя '{person}' или партнёр отсутствуют в списке участников."
                )
            for other in others:
                if person != other:
                    conflicts[person].add(other)
                    conflicts[other].add(person)
                    # Also create a LimitConstraint for each pair with high priority
                    constraint = LimitConstraint.from_pair(person, other, priority=0)
                    # Avoid duplicates
                    if constraint not in limit_constraints:
                        limit_constraints.append(constraint)
    
    # Calculate target sizes
    base_size, extra = divmod(len(all_people), n)
    size_targets = [base_size + (1 if i < extra else 0) for i in range(n)]
    max_size = base_size + (1 if extra > 0 else 0)
    
    # Validate conflicts don't exceed max group size
    for person, conflict_list in conflicts.items():
        if len(conflict_list) >= max_size:
            raise RuntimeError(
                f"Конфликт '{person}' ({len(conflict_list)}) > макс. размера группы ({max_size})."
            )
    
    # Calculate target role distributions
    role_totals = defaultdict(int)
    for role in roles.values():
        role_totals[role] += 1
    
    role_targets = {
        role: [base + (1 if i < remainder else 0) for i in range(n)]
        for role, count in role_totals.items()
        for base, remainder in [divmod(count, n)]
    }
    
    # Calculate target gender distributions
    gender_totals = defaultdict(int)
    for gender in genders.values():
        gender_totals[gender] += 1
    
    gender_targets = {
        gender: [base + (1 if i < remainder else 0) for i in range(n)]
        for gender, count in gender_totals.items()
        for base, remainder in [divmod(count, n)]
    }
    
    # Build configuration
    config = {
        'all': all_people,
        'roles': roles,
        'genders': genders,
        'conflicts': conflicts,
        'size_tgt': size_targets,
        'role_tgt': role_targets,
        'gender_tgt': gender_targets,
        'strict_r': strict_r,
        'strict_g': strict_g,
        'g_num': n,
    }
    
    # Generate seeds for attempts
    seeds = [used_seed + i for i in range(max_attempts)]
    
    # Run attempts
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_run_attempt, s, config): i for i, s in enumerate(seeds)}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    result.attempts = futures[future] + 1
                    return result
    else:
        for i, s in enumerate(seeds):
            result = _run_attempt(s, config)
            if result:
                result.attempts = i + 1
                return result
    
    raise RuntimeError(f"Сборка не удалась за {max_attempts} попыток. Seed: {used_seed}")
