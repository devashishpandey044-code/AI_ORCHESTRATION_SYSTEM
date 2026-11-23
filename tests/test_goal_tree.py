def _create(client, auth, **overrides):
    body = {"title": "Vision", "horizon": "vision"} | overrides
    r = client.post("/goals", json=body, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def _titles(nodes):
    # sorted() on purpose: SQLite timestamps have 1-second resolution, so creation
    # order is not guaranteed inside tests.
    return sorted(n["title"] for n in nodes)


def test_tree_requires_auth(client):
    assert client.get("/goals/tree").status_code == 401


def test_tree_empty(client, auth):
    r = client.get("/goals/tree", headers=auth)
    assert r.status_code == 200
    assert r.json() == []


def test_tree_nests_goals(client, auth):
    vision = _create(client, auth, title="Get SDE job")
    m1 = _create(client, auth, title="Finish backend", horizon="milestone", parent_id=vision["id"])
    _create(client, auth, title="Practice DSA", horizon="milestone", parent_id=vision["id"])
    _create(client, auth, title="Auth + CRUD", horizon="weekly", parent_id=m1["id"])

    roots = client.get("/goals/tree", headers=auth).json()
    assert len(roots) == 1
    root = roots[0]
    assert root["title"] == "Get SDE job"
    assert _titles(root["children"]) == ["Finish backend", "Practice DSA"]

    backend = next(c for c in root["children"] if c["title"] == "Finish backend")
    assert _titles(backend["children"]) == ["Auth + CRUD"]

    dsa = next(c for c in root["children"] if c["title"] == "Practice DSA")
    assert dsa["children"] == []


def test_goals_without_parent_are_roots(client, auth):
    _create(client, auth, title="A")
    _create(client, auth, title="B", horizon="milestone")  # no parent
    roots = client.get("/goals/tree", headers=auth).json()
    assert _titles(roots) == ["A", "B"]


def test_tree_only_includes_own_goals(client, auth, other_auth):
    _create(client, auth, title="Mine")
    _create(client, other_auth, title="Bobs")
    roots = client.get("/goals/tree", headers=auth).json()
    assert _titles(roots) == ["Mine"]


def test_tree_node_has_goal_fields(client, auth):
    _create(client, auth, title="Mine", confidence=0.7)
    node = client.get("/goals/tree", headers=auth).json()[0]
    assert node["confidence"] == 0.7
    assert node["horizon"] == "vision"
    assert node["status"] == "active"
    assert node["children"] == []
