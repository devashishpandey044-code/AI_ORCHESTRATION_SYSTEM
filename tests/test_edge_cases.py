def _goal(client, auth, **overrides):
    body = {"title": "Goal", "horizon": "vision"} | overrides
    return client.post("/goals", json=body, headers=auth)


def test_title_length_boundary(client, auth):
    assert _goal(client, auth, title="a" * 200).status_code == 201
    assert _goal(client, auth, title="a" * 201).status_code == 422
