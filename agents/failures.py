"""Exception levee quand un agent ne peut pas evaluer.

Permet de distinguer une note basse (jugement) d'une absence de note
(panne). La reponse concernee reste marquee non evaluee.
"""


class EvaluationFailed(RuntimeError):
    """Un agent n'a pas pu produire de jugement."""
