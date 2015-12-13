import json

cached_user_db = None


def get_user_db():
    global cached_user_db
    if cached_user_db is None:
        cached_user_db = {}
    return cached_user_db

def get_user_for_service(username, service):
    resolved_user = None
    resolved_user_key = get_user_db().get(username)

    if resolved_user_key:
        resolved_user = resolved_user_key.get(service, username)
    else:
        for user, dict in get_user_db().iteritems():
            if username in dict.values():
                resolved_user = dict[service]
                break

    return resolved_user
