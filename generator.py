# generator.py
"""Group generation module for balanced participant distribution."""

import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Union, Literal
from concurrent.futures import ThreadPoolExecutor, as_completed


@dataclass(frozen=True, eq=True)
class LimitConstraint:
    """Represents a limit constraint with type and priority.
    
    There are two types of constraints:
    
    1. MANY_TO_MANY: All members in this constraint cannot be in the same group.
       Any subset of 2 or more members from this group is forbidden.
       Example: A-B-C means no two of {A,B,C} can be together.
       
    2. ONE_TO_MANY: The 'source' member cannot be with any of the 'targets',
       but targets can be together.
       Example: A -> B,C means A cannot be with B or C, but B and C can be together.
    
    Attributes:
        members: Set of all participant names involved in this constraint
        constraint_type: Either 'many_to_many' or 'one_to_many'
        source: For one_to_many, the person who cannot be with others (None for many_to_many)
        targets: For one_to_many, the set of people the source cannot be with (empty for many_to_many)
        priority: Lower number = higher priority
    """
    members: frozenset
    constraint_type: Literal['many_to_many', 'one_to_many']
    source: Optional[str] = None
    targets: frozenset = frozenset()
    priority: int = 0
    
    @classmethod
    def create_many_to_many(cls, members: list[str], priority: int = 0) -> 'LimitConstraint':
        """Create a many-to-many constraint.
        
        All members cannot be in the same group. Any pair or subset is forbidden.
        
        Args:
            members: List of member names (at least 2)
            priority: Priority level (lower = higher priority)
        """
        if len(members) < 2:
            raise ValueError("A many-to-many constraint must have at least 2 members")
        return cls(
            members=frozenset(members),
            constraint_type='many_to_many',
            source=None,
            targets=frozenset(),
            priority=priority
        )
    
    @classmethod
    def create_one_to_many(cls, source: str, targets: list[str], priority: int = 0) -> 'LimitConstraint':
        """Create a one-to-many constraint.
        
        The source cannot be with any target, but targets can be together.
        
        Args:
            source: The person who cannot be with others
            targets: List of people the source cannot be with (at least 1)
            priority: Priority level (lower = higher priority)
        """
        if not targets:
            raise ValueError("A one-to-many constraint must have at least 1 target")
        all_members = [source] + list(targets)
        if len(set(all_members)) != len(all_members):
            raise ValueError("Source cannot be in targets")
        return cls(
            members=frozenset(all_members),
            constraint_type='one_to_many',
            source=source,
            targets=frozenset(targets),
            priority=priority
        )
    
    def get_forbidden_pairs(self) -> set[tuple[str, str]]:
        """Get all forbidden pairs from this constraint.
        
        Returns a set of (person1, person2) tuples where person1 < person2 alphabetically.
        """
        pairs = set()
        if self.constraint_type == 'many_to_many':
            # All pairs are forbidden
            members_list = sorted(self.members)
            for i, m1 in enumerate(members_list):
                for m2 in members_list[i+1:]:
                    pairs.add((m1, m2))
        elif self.constraint_type == 'one_to_many':
            # Only source-target pairs are forbidden
            if self.source:
                for target in self.targets:
                    pair = tuple(sorted([self.source, target]))
                    pairs.add(pair)
        return pairs
    
    def is_violated_by(self, group_set: set[str]) -> bool:
        """Check if this constraint is violated by a group.
        
        For many_to_many: violated if 2+ members are in the group
        For one_to_many: violated if source AND any target are in the group
        """
        if self.constraint_type == 'many_to_many':
            # Violated if 2 or more members are in the same group
            return len(self.members & group_set) >= 2
        elif self.constraint_type == 'one_to_many':
            # Violated if source is in group AND any target is also in group
            if self.source and self.source in group_set:
                return bool(self.targets & group_set)
            return False
        return False


@dataclass
class GroupingResult:
    """Result of group generation attempt."""
    
    groups: list[list[str]]
    attempts: int
    status: str
    warnings: list[str]
    used_seed: int
    balance_metrics: dict = field(default_factory=dict)
    strategy_used: str = "balanced"
    configuration_summary: dict = field(default_factory=dict)


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
                or a list of LimitConstraint objects (new format with many_to_many and one_to_many types)
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
        # Build pairwise conflicts from all constraints
        for constraint in limit_constraints:
            for pair in constraint.get_forbidden_pairs():
                conflicts[pair[0]].add(pair[1])
                conflicts[pair[1]].add(pair[0])
    else:
        # Legacy format: dict[str, list[str]]
        for person, others in limits.items():
            for other in others:
                conflicts[person].add(other)
                conflicts[other].add(person)
    
    # Check no pairwise conflicts within groups
    for group in groups:
        group_set = set(group)
        for person in group:
            if conflicts[person] & group_set:
                return False
    
    # Check multi-member constraints using is_violated_by
    for constraint in limit_constraints:
        for group in groups:
            group_set = set(group)
            if constraint.is_violated_by(group_set):
                return False
    
    # Check role balance
    if strict_r:
        role_totals = defaultdict(int)
        for role in roles.values():
            role_totals[role] += 1
        
        role_targets = {
            role: [base + (1 if i < remainder else 0) for i in range(len(groups))]
            for role, count in role_totals.items()
            for base, remainder in [divmod(count, len(groups))]
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
            gender: [base + (1 if i < remainder else 0) for i in range(len(groups))]
            for gender, count in gender_totals.items()
            for base, remainder in [divmod(count, len(groups))]
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
    strategy = config.get('strategy', 'balanced')
    mix_intensity = config.get('mix_intensity', 5)
    newbies = config.get('newbies', [])
    experts = config.get('experts', [])
    
    # Strategy-specific pool ordering
    pool = list(all_people)
    
    if strategy == "random":
        # Pure random - just shuffle
        rng.shuffle(pool)
        # For random strategy, disable strict balance
        strict_r_local = False
        strict_g_local = False
    elif strategy == "newbie_friendly":
        # Put newbies first so they get distributed evenly
        newbie_set = set(newbies)
        newbies_in_pool = [p for p in pool if p in newbie_set]
        others = [p for p in pool if p not in newbie_set]
        rng.shuffle(newbies_in_pool)
        rng.shuffle(others)
        pool = newbies_in_pool + others
        strict_r_local = strict_r
        strict_g_local = strict_g
    elif strategy == "expert_lead":
        # Put experts first to ensure each group gets one
        expert_set = set(experts)
        experts_in_pool = [p for p in pool if p in expert_set]
        others = [p for p in pool if p not in expert_set]
        rng.shuffle(experts_in_pool)
        rng.shuffle(others)
        pool = experts_in_pool + others
        strict_r_local = strict_r
        strict_g_local = strict_g
    else:  # balanced
        # Sort by number of conflicts (most constrained first)
        pool = sorted(all_people, key=lambda p: len(conflicts[p]), reverse=True)
        rng.shuffle(pool)
        strict_r_local = strict_r
        strict_g_local = strict_g
    
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
            if constraint.is_violated_by(group_set):
                return False
        return True
    
    # Assign participants to groups
    for person in pool:
        role = roles[person]
        gender = genders[person]
        
        # For random strategy, skip balance checks
        if strategy == "random":
            valid_groups = [
                i for i in range(num_groups)
                if len(groups[i]) < size_targets[i]
                and not any(person in conflicts[member] for member in groups[i])
                and check_multi_member_constraints(i, person)
            ]
        else:
            # Find valid groups with balance constraints
            valid_groups = [
                i for i in range(num_groups)
                if len(groups[i]) < size_targets[i]
                and (not strict_r_local or group_role_counts[i][role] < role_targets[role][i])
                and (not strict_g_local or group_gender_counts[i][gender] < gender_targets[gender][i])
                and not any(person in conflicts[member] for member in groups[i])
                and check_multi_member_constraints(i, person)
            ]
        
        # Relax constraints if needed
        if not valid_groups and (strict_r_local or strict_g_local):
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
    # Skip optimization for random strategy
    if strategy != "random":
        # Adjust iterations based on mix_intensity
        max_iterations = int(150 * (mix_intensity / 5))
        stagnation_limit = int(25 * (mix_intensity / 5))
        
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
        
        for _ in range(max_iterations):
            if stagnation_counter >= stagnation_limit:
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
                    if constraint.is_violated_by(group_set):
                        return True
                return False
            
            if would_violate_multi_member(g2, p1):
                continue
            if would_violate_multi_member(g1, p2):
                continue
            
            # Check role/gender capacity constraints
            if strict_r_local and (group_role_counts[g2][r1] + 1 > role_targets[r1][g2] 
                             or group_role_counts[g1][r2] + 1 > role_targets[r2][g1]):
                continue
            if strict_g_local and (group_gender_counts[g2][gn1] + 1 > gender_targets[gn1][g2] 
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
    strategy: Literal["balanced", "random", "newbie_friendly", "expert_lead"] = "balanced",
    mix_intensity: int = 5,
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
        strategy: Generation strategy:
            - "balanced": Default balanced distribution (role/gender/size)
            - "random": Pure random assignment (ignores role/gender balance)
            - "newbie_friendly": Prioritizes spreading newbies evenly with expert support
            - "expert_lead": Each group gets at least one expert if possible
        mix_intensity: How aggressively to mix participants (1-10, higher = more mixing attempts)
        
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
        # Validate all members exist and build pairwise conflicts
        for constraint in limit_constraints:
            if not all(member in all_set for member in constraint.members):
                missing = [m for m in constraint.members if m not in all_set]
                raise ValueError(
                    f"Имя '{missing[0]}' отсутствует в списке участников."
                )
            # Build pairwise conflicts from all constraint types
            for pair in constraint.get_forbidden_pairs():
                conflicts[pair[0]].add(pair[1])
                conflicts[pair[1]].add(pair[0])
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
                    constraint = LimitConstraint.create_many_to_many([person, other], priority=0)
                    # Avoid duplicates
                    if constraint not in limit_constraints:
                        limit_constraints.append(constraint)
    
    # Calculate target sizes
    base_size, extra = divmod(len(all_people), n)
    size_targets = [base_size + (1 if i < extra else 0) for i in range(n)]
    max_size = base_size + (1 if extra > 0 else 0)
    
    # Validate conflicts don't exceed max group size
    # Only check pairwise conflicts from legacy dict format or simple pairs
    # For multi-member constraints (>2 members), the constraint itself handles distribution
    for person, conflict_list in conflicts.items():
        # Check if this is a simple pairwise conflict (not part of a larger multi-member constraint)
        # We only raise error if ALL conflicts for this person are true pairwise conflicts
        is_pure_pairwise = True
        for constraint in limit_constraints:
            if person in constraint.members and len(constraint.members) > 2:
                # This person is part of a multi-member constraint, skip strict validation
                is_pure_pairwise = False
                break
        
        if is_pure_pairwise and len(conflict_list) >= max_size:
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
        'strategy': strategy,
        'mix_intensity': mix_intensity,
        'newbies': newbies or [],
        'experts': experts or [],
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
                    result.strategy_used = strategy
                    result.configuration_summary = {
                        'num_groups': n,
                        'total_participants': len(all_people),
                        'num_experts': len(experts or []),
                        'num_newbies': len(newbies or []),
                        'strict_roles': strict_r,
                        'strict_genders': strict_g,
                    }
                    return result
    else:
        for i, s in enumerate(seeds):
            result = _run_attempt(s, config)
            if result:
                result.attempts = i + 1
                result.strategy_used = strategy
                result.configuration_summary = {
                    'num_groups': n,
                    'total_participants': len(all_people),
                    'num_experts': len(experts or []),
                    'num_newbies': len(newbies or []),
                    'strict_roles': strict_r,
                    'strict_genders': strict_g,
                }
                return result
    
    raise RuntimeError(f"Сборка не удалась за {max_attempts} попыток. Seed: {used_seed}")
