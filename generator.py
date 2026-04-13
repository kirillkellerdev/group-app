# generator.py
"""Group generation module for balanced participant distribution."""

import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


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
    limits: dict[str, list[str]],
    roles: dict[str, str],
    genders: dict[str, str],
    strict_r: bool = True,
    strict_g: bool = True,
) -> bool:
    """Verify that generated groups meet all constraints.
    
    Args:
        groups: List of groups, each containing participant names
        limits: Dictionary mapping participants to lists of people they can't be grouped with
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
    
    # Build conflict map
    conflicts = defaultdict(set)
    for person, others in limits.items():
        for other in others:
            conflicts[person].add(other)
    
    # Check no conflicts within groups
    for group in groups:
        group_set = set(group)
        for person in group:
            if conflicts[person] & group_set:
                return False
    
    num_groups = len(groups)
    
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
        ]
        
        # Relax constraints if needed
        if not valid_groups and (strict_r or strict_g):
            valid_groups = [
                i for i in range(num_groups)
                if len(groups[i]) < size_targets[i]
                and not any(person in conflicts[member] for member in groups[i])
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
    limits: Optional[dict[str, list[str]]] = None,
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
        limits: Optional dictionary mapping participants to lists of people they can't be with
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
    
    # Build conflict map
    limits = limits or {}
    conflicts = defaultdict(set)
    
    for person, others in limits.items():
        if person not in all_set or not all(other in all_set for other in others):
            raise ValueError(
                f"Имя '{person}' или партнёр отсутствуют в списке участников."
            )
        for other in others:
            if person != other:
                conflicts[person].add(other)
                conflicts[other].add(person)
    
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
