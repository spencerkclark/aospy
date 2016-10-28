from aospy import Proj

from .models import im


example = Proj(
    'example',
    direc_out='example-results',
    models=(im,)
)
