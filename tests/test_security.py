from framework.security import permission_matches


def test_permission_wildcards():
    assert permission_matches("*", "anything.here")
    assert permission_matches("notes.*", "notes.read")
    assert not permission_matches("notes.read", "notes.write")
