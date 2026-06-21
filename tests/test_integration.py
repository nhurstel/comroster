def test_add_publish_appears_on_display(client, app):
    client.post("/admin/setup", data={"password": "motdepasse8"})
    g = client.post("/api/groups", json={"name": "Plateau", "color": "#00A8E8"}).get_json()
    client.post("/api/people", json={"role": "HF", "beltpack": "12", "group_id": g["id"]})
    # avant publication : le publié est vide
    assert app.extensions["storage"].load_published() is None
    client.post("/api/publish")
    published = app.extensions["storage"].load_published()
    assert published["people"][0]["beltpack"] == "12"
    assert published["groups"][0]["name"] == "Plateau"
