import numpy as np
import math

# Constants
START_ELO = 1200
K_GLOBAL = 16
K_GAME = 12
PROVISIONAL_GAMES = 4
ALPHA = 5  # Experience weighting

def experience_modifier(games_played):
    return math.log(1 + games_played)

def expected_score(player_rating, opp_rating, exp_modifier=0):
    return 1 / (1 + 10 ** ((opp_rating + ALPHA*exp_modifier - player_rating)/400))

def pairwise_elo_update(ratings, ranks, games_played, provisional_flags, K):
    """
    ratings: dict {player_name: rating}
    ranks: dict {player_name: rank (1=highest)}
    games_played: dict {player_name: num games played}
    provisional_flags: dict {player_name: True/False}
    K: K-factor
    """
    delta = {p:0 for p in ratings}
    players = list(ranks.keys())
    N = len(players)
    
    for i in range(N):
        pi = players[i]
        Ri = ratings[pi]
        exp_i = experience_modifier(games_played[pi])
        for j in range(i+1, N):
            pj = players[j]
            Rj = ratings[pj]
            exp_j = experience_modifier(games_played[pj])
            
            # Actual score
            if ranks[pi] < ranks[pj]:
                S_ij = 1
                S_ji = 0
            elif ranks[pi] == ranks[pj]:
                S_ij = S_ji = 0.5
            else:
                S_ij = 0
                S_ji = 1
                
            # Expected score
            # Global Elo: use provisional logic
            if K == K_GLOBAL:
                Rj_effective = Rj if not provisional_flags[pj] else START_ELO
                Ri_effective = Ri if not provisional_flags[pi] else START_ELO
                E_ij = expected_score(Ri_effective, Rj_effective, exp_j)
                E_ji = expected_score(Rj_effective, Ri_effective, exp_i)
            else:
                # Game-specific Elo: normal
                E_ij = expected_score(Ri, Rj, exp_j)
                E_ji = expected_score(Rj, Ri, exp_i)
                
            delta[pi] += K * (S_ij - E_ij)
            delta[pj] += K * (S_ji - E_ji)
    
    # Update ratings
    new_ratings = {p: ratings[p] + delta[p] for p in ratings}
    return new_ratings
