import uuid


def _create(client, auth, **overrides):
    body = {
        "title": "Data Structures class",
        "kind": "fixed_commitment",
        "days_of_week": [0, 2, 4],
        "start_time": "09:00",
        "end_time": "10:30",
    } | overrides
    return client.post("/constraints", json=body, headers=auth)


def test_requires_auth(client):
    assert client.get("/constraints").status_code == 401


def test_create_fixed_commitment(client, auth):
    r = _create(client, auth, days_of_week=[4, 0, 2, 2])
    assert r.status_code == 201
    body = r.json()
    assert body["days_of_week"] == [0, 2, 4]  # sorted + de-duplicated
    assert body["is_hard"] is True
    assert body["active"] is True
    assert body["start_time"].startswith("09:00")


def test_fixed_commitment_requires_start_before_end(client, auth):
    assert _create(client, auth, start_time="11:00", end_time="10:00").status_code == 422
    assert _create(client, auth, start_time="10:00", end_time="10:00").status_code == 422


def test_fixed_commitment_requires_times_and_days(client, auth):
    assert _create(client, auth, start_time=None, end_time=None).status_code == 422
    assert _create(client, auth, days_of_week=[]).status_code == 422


def test_sleep_may_cross_midnight(client, auth):
    r = _create(
        client, auth, title="Sleep", kind="sleep",
        days_of_week=[0, 1, 2, 3, 4, 5, 6], start_time="23:00", end_time="07:00",
    )
    assert r.status_code == 201


def test_capacity_limit_requires_max_minutes_and_defaults_all_days(client, auth):
    bad = client.post(
        "/constraints", json={"title": "Max deep work", "kind": "capacity_limit"}, headers=auth
    )
    assert bad.status_code == 422

    ok = client.post(
        "/constraints",
        json={"title": "Max deep work", "kind": "capacity_limit", "max_minutes_per_day": 240},
        headers=auth,
    )
    assert ok.status_code == 201
    assert ok.json()["days_of_week"] == [0, 1, 2, 3, 4, 5, 6]


def test_invalid_day_rejected(client, auth):
    assert _create(client, auth, days_of_week=[7]).status_code == 422
    assert _create(client, auth, days_of_week=[-1]).status_code == 422


def test_max_minutes_bounds(client, auth):
    body = {"title": "x", "kind": "capacity_limit"}
    assert client.post("/constraints", json=body | {"max_minutes_per_day": 0}, headers=auth).status_code == 422
    assert client.post("/constraints", json=body | {"max_minutes_per_day": 1441}, headers=auth).status_code == 422


def test_patch_revalidates_merged_state(client, auth):
    c = _create(client, auth).json()  # 09:00 - 10:30
    bad = client.patch(f"/constraints/{c['id']}", json={"start_time": "11:00"}, headers=auth)
    assert bad.status_code == 422

    ok = client.patch(
        f"/constraints/{c['id']}",
        json={"start_time": "08:00", "active": False, "is_hard": False},
        headers=auth,
    )
    assert ok.status_code == 200
    assert ok.json()["active"] is False
    assert ok.json()["is_hard"] is False
    assert ok.json()["start_time"].startswith("08:00")


def test_patch_rejects_null_required_fields(client, auth):
    c = _create(client, auth).json()
    assert client.patch(f"/constraints/{c['id']}", json={"title": None}, headers=auth).status_code == 422


def test_list_scoped_and_filterable(client, auth, other_auth):
    _create(client, auth, title="Class")
    _create(client, auth, title="Sleep", kind="sleep", days_of_week=[0], start_time="23:00", end_time="07:00")
    _create(client, other_auth, title="Bob's class")

    mine = client.get("/constraints", headers=auth).json()
    assert {c["title"] for c in mine} == {"Class", "Sleep"}

    sleeps = client.get("/constraints?kind=sleep", headers=auth).json()
    assert [c["title"] for c in sleeps] == ["Sleep"]


def test_users_cannot_access_each_others_constraints(client, auth, other_auth):
    c = _create(client, auth).json()
    cid = c["id"]
    assert client.get(f"/constraints/{cid}", headers=other_auth).status_code == 404
    assert client.patch(f"/constraints/{cid}", json={"title": "x"}, headers=other_auth).status_code == 404
    assert client.delete(f"/constraints/{cid}", headers=other_auth).status_code == 404
    assert client.get(f"/constraints/{cid}", headers=auth).status_code == 200


def test_delete_constraint(client, auth):
    c = _create(client, auth).json()
    assert client.delete(f"/constraints/{c['id']}", headers=auth).status_code == 204
    assert client.get(f"/constraints/{c['id']}", headers=auth).status_code == 404


def test_unknown_constraint_404(client, auth):
    assert client.get(f"/constraints/{uuid.uuid4()}", headers=auth).status_code == 404
