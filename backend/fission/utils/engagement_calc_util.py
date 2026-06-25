like_weight = 1
comment_weight = 2
share_weight = 4

def engagement_calc(likes, comments, shares):
    engagement = (likes * like_weight + comments * comment_weight + shares * share_weight)
    return engagement