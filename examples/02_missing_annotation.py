"""Any from a function without annotations, travelling through attributes."""


def load_user(user_id):
    return {"id": user_id}


class Session:
    def __init__(self, user_id: int) -> None:
        self.user = load_user(user_id)

    def name(self) -> str:
        return self.user.profile.name


reveal_any_source(Session(1).user)
