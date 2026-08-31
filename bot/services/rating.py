def get_k_factor(matches_played: int) -> float:
    """
    Calcula el factor K decreciente de 0.24 a 0.10 en 10 partidos.
    A mayor K, más cambia el nivel (ideal para calibrar usuarios nuevos).
    """
    k = 0.24 - (0.014 * matches_played)
    return max(0.10, round(k, 4))


def calculate_new_levels(
    p1_levels: list[float], 
    p2_levels: list[float], 
    sets_p1: int, 
    sets_p2: int,
    matches_played: list[int]
) -> tuple[list[float], list[float]]:
    """
    Calcula la variación de nivel de cada jugador basándose en:
    - La media del equipo.
    - La probabilidad esperada de victoria.
    - La contundencia del resultado (S).
    - El factor K decreciente de cada jugador.
    """
    # 1. Medias de nivel de cada pareja
    r_p1 = sum(p1_levels) / len(p1_levels) if p1_levels else 0
    r_p2 = sum(p2_levels) / len(p2_levels) if p2_levels else 0

    # 2. Expectativa de victoria (Probabilidad E)
    e_p1 = 1.0 / (1.0 + 10 ** (r_p2 - r_p1))
    e_p2 = 1.0 - e_p1

    # 3. Ponderación del resultado real (S) por margen de sets
    if sets_p1 > sets_p2:
        s_p1, s_p2 = (1.0, 0.0) if sets_p2 == 0 else (0.85, 0.15)
    elif sets_p2 > sets_p1:
        s_p2, s_p1 = (1.0, 0.0) if sets_p1 == 0 else (0.85, 0.15)
    else:
        # En caso extremo de empate anómalo (previene errores matemáticos)
        s_p1, s_p2 = 0.5, 0.5

    # 4. Actualización Pareja 1
    new_p1 = []
    for i, level in enumerate(p1_levels):
        k = get_k_factor(matches_played[i])
        # Fórmula: Nivel Actual + K * (Resultado - Expectativa)
        new_val = max(0.0, min(6.0, round(level + k * (s_p1 - e_p1), 2)))
        new_p1.append(new_val)

    # 5. Actualización Pareja 2
    new_p2 = []
    for i, level in enumerate(p2_levels):
        # Desplazamos el índice 'i' para leer los partidos jugados de la Pareja 2
        k = get_k_factor(matches_played[len(p1_levels) + i])
        new_val = max(0.0, min(6.0, round(level + k * (s_p2 - e_p2), 2)))
        new_p2.append(new_val)

    return new_p1, new_p2