import math

def calculate_k_factor(matches_played: int) -> float:
    """K factor progresivo para jugadores irregulares (0.24 -> 0.10 en 10 partidos)."""
    return max(0.10, 0.24 - (0.014 * matches_played))

def update_team_ratings(
    team1_players: list[tuple[int, float, int]],  # [(id, level, matches_played)]
    team2_players: list[tuple[int, float, int]], 
    team1_sets: int, 
    team2_sets: int
) -> dict[int, float]:
    """Calcula las nuevas puntuaciones con la curva logística ELO y bonus de victoria."""
    avg_t1 = sum(p[1] for p in team1_players) / max(len(team1_players), 1)
    avg_t2 = sum(p[1] for p in team2_players) / max(len(team2_players), 1)

    diff = avg_t2 - avg_t1
    expected_t1 = 1.0 / (1.0 + math.pow(10, diff / 1.5))
    expected_t2 = 1.0 - expected_t1

    actual_t1 = 1.0 if team1_sets > team2_sets else 0.0
    actual_t2 = 1.0 - actual_t1
    
    # Bonus/Malus fijo de victoria según requerimientos
    bonus_t1 = 0.05 if actual_t1 == 1.0 else -0.05
    bonus_t2 = 0.05 if actual_t2 == 1.0 else -0.05

    new_ratings = {}

    for uid, lvl, played in team1_players:
        k = calculate_k_factor(played)
        delta = k * (actual_t1 - expected_t1) + bonus_t1
        new_ratings[uid] = round(max(0.0, min(6.0, lvl + delta)), 2)

    for uid, lvl, played in team2_players:
        k = calculate_k_factor(played)
        delta = k * (actual_t2 - expected_t2) + bonus_t2
        new_ratings[uid] = round(max(0.0, min(6.0, lvl + delta)), 2)

    return new_ratings