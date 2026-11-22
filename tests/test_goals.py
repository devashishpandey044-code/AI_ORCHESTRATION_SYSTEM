import uuid


def _create(client, auth, **overrides):
    body = {"title": "Get a software developer job", "horizon": "vision"} | overrides
    return client.post("/goals", json=body, headers=auth)


def test_requires_auth(client):
    assert client.get("/goals").status_code == 401
    assert client.post("/goals", json={"title": "x", "horizon": "vision"}).status_code == 401


def test_create_and_get_goal(client, auth):
    r = _create(client, auth, description="Land an SDE offer", confidence=0.8)
    assert r.status_code == 201
    goal = r.json()
    assert goal["status"] == "active"
    assert goal["source"] == "stated"
    assert goal["confidence"] == 0.8
    assert goal["parent_id"] is None

    r = client.get(f"/goals/{goal['id']}", headers=auth)
    assert r.status_code == 200
    assert r.json()["title"] == "Get a software developer job"


def test_full_hierarchy(client, auth):
    vision = _create(client, auth, horizon="vision").json()
    milestone = _create(client, auth, title="Finish backend project", horizon="milestone",
                        parent_id=vision["id"])
    assert milestone.status_code == 201
    weekly = _create(client, auth, title="Auth + CRUD", horizon="weekly",
                     parent_id=milestone.json()["id"])
    assert weekly.status_code == 201
    daily = _create(client, auth, title="Write migrations", horizon="daily",
                    parent_id=weekly.json()["id"])
    assert daily.status_code == 201


def test_cannot_nest_higher_or_same_horizon_under_lower(client, auth):
    milestone = _create(client, auth, title="M", horizon="milestone").json()
    # vision under milestone
    r = _create(client, auth, title="V", horizon="vision", parent_id=milestone["id"])
    assert r.status_code == 422
    # milestone under milestone
    r = _create(client, auth, title="M2", horizon="milestone", parent_id=milestone["id"])
    assert r.status_code == 422


def test_parent_must_exist_and_belong_to_user(client, auth, other_auth):
    alice_goal = _create(client, auth).json()
    r = _create(client, other_auth, title="M", horizon="milestone", parent_id=alice_goal["id"])
    assert r.status_code == 404
    r = _create(client, auth, title="M", horizon="milestone", parent_id=str(uuid.uuid4()))
    assert r.status_code == 404


def test_confidence_range_validated(client, auth):
    assert _create(client, auth, confidence=1.5).status_code == 422
    assert _create(client, auth, confidence=-0.1).status_code == 422


def test_users_cannot_access_each_others_goals(client, auth, other_auth):
    goal = _create(client, auth).json()
    gid = goal["id"]
    assert client.get(f"/goals/{gid}", headers=other_auth).status_code == 404
    assert client.patch(f"/goals/{gid}", json={"title": "hacked"}, headers=other_auth).status_code == 404
    assert client.post(f"/goals/{gid}/review", headers=other_auth).status_code == 404
    assert client.delete(f"/goals/{gid}", headers=other_auth).status_code == 404
    # still intact for the owner
    assert client.get(f"/goals/{gid}", headers=auth).json()["title"] == goal["title"]


def test_list_is_scoped_and_filterable(client, auth, other_auth):
    _create(client, auth, title="V", horizon="vision")
    _create(client, auth, title="W", horizon="weekly")
    _create(client, other_auth, title="Bob's", horizon="vision")

    all_mine = client.get("/goals", headers=auth).json()
    assert {g["title"] for g in all_mine} == {"V", "W"}

    weekly = client.get("/goals?horizon=weekly", headers=auth).json()
    assert [g["title"] for g in weekly] == ["W"]

    assert len(client.get("/goals?limit=1", headers=auth).json()) == 1


def test_list_filter_by_status_and_parent(client, auth):
    vision = _create(client, auth).json()
    child = _create(client, auth, title="C", horizon="milestone", parent_id=vision["id"]).json()
    client.patch(f"/goals/{child['id']}", json={"status": "paused"}, headers=auth)

    by_status = client.get("/goals?status=paused", headers=auth).json()
    assert [g["id"] for g in by_status] == [child["id"]]

    by_parent = client.get(f"/goals?parent_id={vision['id']}", headers=auth).json()
    assert [g["id"] for g in by_parent] == [child["id"]]


def test_patch_updates_fields(client, auth):
    goal = _create(client, auth).json()
    r = client.patch(
        f"/goals/{goal['id']}",
        json={"status": "completed", "confidence": 0.5, "title": "Renamed"},
        headers=auth,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["confidence"] == 0.5
    assert body["title"] == "Renamed"


def test_patch_rejects_null_required_fields_and_bad_values(client, auth):
    goal = _create(client, auth).json()
    gid = goal["id"]
    assert client.patch(f"/goals/{gid}", json={"title": None}, headers=auth).status_code == 422
    assert client.patch(f"/goals/{gid}", json={"confidence": 2}, headers=auth).status_code == 422
    assert client.patch(f"/goals/{gid}", json={"status": "nonsense"}, headers=auth).status_code == 422


def test_patch_parent_revalidated(client, auth):
    vision = _create(client, auth).json()
    daily = _create(client, auth, title="D", horizon="daily").json()
    ok = client.patch(f"/goals/{daily['id']}", json={"parent_id": vision["id"]}, headers=auth)
    assert ok.status_code == 200
    assert ok.json()["parent_id"] == vision["id"]

    # a vision cannot be moved under a daily goal
    bad = client.patch(f"/goals/{vision['id']}", json={"parent_id": daily["id"]}, headers=auth)
    assert bad.status_code == 422

    # parent can be cleared explicitly
    cleared = client.patch(f"/goals/{daily['id']}", json={"parent_id": None}, headers=auth)
    assert cleared.status_code == 200
    assert cleared.json()["parent_id"] is None


def test_review_sets_timestamp(client, auth):
    goal = _create(client, auth).json()
    assert goal["last_reviewed_at"] is None
    r = client.post(f"/goals/{goal['id']}/review", headers=auth)
    assert r.status_code == 200
    assert r.json()["last_reviewed_at"] is not None


def test_delete_goal_orphans_children(client, auth):
    vision = _create(client, auth).json()
    child = _create(client, auth, title="C", horizon="milestone", parent_id=vision["id"]).json()

    assert client.delete(f"/goals/{vision['id']}", headers=auth).status_code == 204
    assert client.get(f"/goals/{vision['id']}", headers=auth).status_code == 404

    survivor = client.get(f"/goals/{child['id']}", headers=auth)
    assert survivor.status_code == 200
    assert survivor.json()["parent_id"] is None


def test_unknown_goal_returns_404(client, auth):
    assert client.get(f"/goals/{uuid.uuid4()}", headers=auth).status_code == 404
