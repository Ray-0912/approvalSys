def test_healthz_endpoint(authenticated_client):
    response = authenticated_client.get('/healthz')
    assert response.status_code == 200
    assert response.get_json()['data']['status'] == 'ok'
