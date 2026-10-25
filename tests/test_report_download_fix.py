import urllib.request
import json

def run_tests():
    # 1. Test root page
    res = urllib.request.urlopen('http://localhost:8008/app')
    html = res.read().decode('utf-8')
    assert 'report-frame' in html, "report-frame not found in HTML"
    assert 'src="about:blank"' in html, "report-frame does not have src='about:blank'"
    print("TEST 1 PASSED: index.html has report-frame src='about:blank' (no auto-download)")

    # 2. Test /v1/reports/view
    res = urllib.request.urlopen('http://localhost:8008/v1/reports/view?format=html')
    headers = dict(res.headers)
    content = res.read().decode('utf-8')
    assert res.status == 200, f"Expected 200 got {res.status}"
    assert 'text/html' in headers.get('content-type', ''), f"Unexpected content-type: {headers.get('content-type')}"
    assert headers.get('content-disposition') == 'inline', f"Unexpected content-disposition: {headers.get('content-disposition')}"
    assert 'Commercial Performance & Strategic Growth Memorandum' in content, "Report content missing memorandum title"
    print("TEST 2 PASSED: /v1/reports/view returns inline HTML with new white report theme")

    # 3. Test POST /v1/reports for HTML
    req = urllib.request.Request(
        'http://localhost:8008/v1/reports',
        data=json.dumps({'dataset_id': 'ds_reference', 'format': 'html'}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    res = urllib.request.urlopen(req)
    d = json.loads(res.read().decode('utf-8'))
    download_url = d['download_url']
    print(f"POST /v1/reports returned: {download_url}")

    # Fetch the generated report URL (without download=true)
    res_gen = urllib.request.urlopen('http://localhost:8008' + download_url)
    gen_headers = dict(res_gen.headers)
    assert res_gen.status == 200, f"Expected 200 got {res_gen.status}"
    assert 'text/html' in gen_headers.get('content-type', ''), f"Unexpected content-type: {gen_headers.get('content-type')}"
    assert gen_headers.get('content-disposition') == 'inline', f"Expected inline, got {gen_headers.get('content-disposition')}"
    print("TEST 3 PASSED: Generated report served inline without triggering file download")

    # 4. Test explicit download=true
    res_dl = urllib.request.urlopen('http://localhost:8008' + download_url + '&download=true')
    dl_headers = dict(res_dl.headers)
    assert res_dl.status == 200, f"Expected 200 got {res_dl.status}"
    assert 'attachment' in dl_headers.get('content-disposition', ''), f"Expected attachment, got {dl_headers.get('content-disposition')}"
    print("TEST 4 PASSED: Explicit download=true correctly triggers attachment download")

    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    run_tests()
