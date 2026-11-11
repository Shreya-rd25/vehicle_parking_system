import re, json, requests
B = "http://localhost:5055"
results = []

def tok(html):
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None

def rec(sid, name, expected, actual, ok):
    results.append({"id": sid, "name": name, "expected": expected, "actual": actual, "status": "Pass" if ok else "Fail"})

def login(email, pw):
    s = requests.Session()
    r = s.get(B + "/login")
    r = s.post(B + "/login", data={"email": email, "password": pw, "csrf_token": tok(r.text)}, allow_redirects=True)
    return s, r

def post(s, path, page, data=None, **kw):
    t = tok(s.get(B + page).text)
    d = dict(data or {}); d["csrf_token"] = t
    return s.post(B + path, data=d, allow_redirects=False, **kw)

s = requests.Session()
r = s.get(B + "/register")
r = s.post(B + "/register", data={"name": "Sys User", "email": "sys1@test.com", "password": "pass1234", "csrf_token": tok(r.text)}, allow_redirects=True)
rec("SV-01", "Customer registers a new account", "Redirected to login page after registration", f"HTTP {r.status_code}, final URL {r.url.replace(B,'')}", r.url.endswith("/login"))

c1, r = login("sys1@test.com", "pass1234")
rec("SV-02", "Customer logs in", "Dashboard with slot list is shown", f"final URL {r.url.replace(B,'')}, floors shown: {len(re.findall('Floor', r.text))}", "F1-01" in r.text)

r = c1.get(B + "/dashboard")
m = re.search(r'href="(/book/(\d+))"', r.text)
book_url, slot_id = m.group(1), m.group(2)
r = c1.get(B + book_url)
rec("SV-03", "Customer opens booking form from an available slot", "Booking form for the chosen slot is shown", f"HTTP {r.status_code}", r.status_code == 200 and "Book" in r.text)

r = post(c1, "/vehicles", "/vehicles", {"vehicle_number": "KA01SV1234", "vehicle_type": "car"})
r2 = c1.get(B + "/vehicles")
rec("SV-04", "Customer registers a vehicle", "Vehicle appears on My Vehicles page", f"HTTP {r.status_code}", "KA01SV1234" in r2.text)

r = post(c1, "/book", book_url, {"slot_id": slot_id, "vehicle_number": "KA01SV1234", "vehicle_type": "car"})
h = c1.get(B + "/history")
rec("SV-05", "Customer books slot and is checked in", "Redirect to history; active booking with check-in time", f"HTTP {r.status_code} to {r.headers.get('Location')}", r.status_code == 302 and "KA01SV1234" in h.text and "active" in h.text.lower())

d = c1.get(B + "/dashboard")
rec("SV-06", "Booked slot shows as occupied on dashboard", "Slot no longer offered as an available link", "link for booked slot " + ("absent" if f"/book/{slot_id}\"" not in d.text else "present"), f"/book/{slot_id}\"" not in d.text)

c2 = requests.Session()
r = c2.get(B + "/register")
c2.post(B + "/register", data={"name": "Sys Two", "email": "sys2@test.com", "password": "pass1234", "csrf_token": tok(r.text)})
c2, _ = login("sys2@test.com", "pass1234")
t = tok(c2.get(B + "/dashboard").text) or tok(c2.get(B + "/vehicles").text)
r = c2.post(B + "/book", data={"slot_id": slot_id, "vehicle_number": "KA02SV5678", "vehicle_type": "car", "csrf_token": t}, allow_redirects=False)
rec("SV-07", "Second customer tries to book the occupied slot", "Booking rejected (409)", f"HTTP {r.status_code}", r.status_code == 409)

bid = re.search(r'/checkout/(\d+)', h.text).group(1)
t = tok(c2.get(B + "/vehicles").text)
r = c2.post(B + f"/checkout/{bid}", data={"csrf_token": t}, allow_redirects=False)
rec("SV-08", "Other customer tries to check out someone else's booking", "403 Forbidden", f"HTTP {r.status_code}", r.status_code == 403)

r = post(c1, f"/checkout/{bid}", "/history")
h2 = c1.get(B + "/history")
d2 = c1.get(B + "/dashboard")
rec("SV-09", "Owner checks out", "Booking completed and slot available again", f"HTTP {r.status_code}; slot link back on dashboard: {f'/book/{slot_id}\"' in d2.text}", f"/book/{slot_id}\"" in d2.text and "completed" in h2.text.lower())

r = post(c1, f"/checkout/{bid}", "/history")
rec("SV-10", "Repeat check-out of a completed booking", "409 Conflict", f"HTTP {r.status_code}", r.status_code == 409)

r = c1.get(B + "/admin/slots", allow_redirects=False)
rec("SV-11", "Customer opens admin page", "403 Forbidden", f"HTTP {r.status_code}", r.status_code == 403)

an = requests.get(B + "/admin/slots", allow_redirects=False)
rec("SV-12", "Anonymous user opens admin page", "Redirect to login", f"HTTP {an.status_code} to {an.headers.get('Location')}", an.status_code == 302 and "login" in an.headers.get("Location", ""))

a, r = login("admin@vps.com", "admin123")
r = post(a, "/admin/slots", "/admin/slots", {"slot_number": "SV-99", "floor": "4", "vehicle_type": "car"})
pg = a.get(B + "/admin/slots")
rec("SV-13", "Admin adds a slot", "New slot SV-99 listed", f"HTTP {r.status_code}", "SV-99" in pg.text)

r = post(a, "/admin/slots", "/admin/slots", {"slot_number": "SV-99", "floor": "4", "vehicle_type": "car"})
rec("SV-14", "Admin adds a duplicate slot", "Rejected with a message, no second slot", f"HTTP {r.status_code}; SV-99 rows: {a.get(B+'/admin/slots').text.count('SV-99')}", a.get(B + "/admin/slots").text.count("SV-99") == 1)

d = a.get(B + "/dashboard")
m = re.search(r'href="(/book/(\d+))"', c1.get(B + "/dashboard").text)
r = post(c1, "/book", m.group(1), {"slot_id": m.group(2), "vehicle_number": "KA01SV1234", "vehicle_type": "car"})
ab = a.get(B + "/admin/bookings")
bid2 = re.search(r'/admin/checkout/(\d+)', ab.text)
rec("SV-15", "Admin views active bookings", "Active booking listed with force check-out option", f"force check-out buttons: {len(re.findall('/admin/checkout/', ab.text))}", bool(bid2))
r = post(a, f"/admin/checkout/{bid2.group(1)}", "/admin/bookings")
ab2 = a.get(B + "/admin/bookings")
rec("SV-16", "Admin force check-out", "Booking completed and removed from active list", f"HTTP {r.status_code}", "/admin/checkout/" not in ab2.text)

sid = re.search(r'/admin/slots/(\d+)/delete', a.get(B + "/admin/slots").text)
ids = re.findall(r'/admin/slots/(\d+)/delete', a.get(B + "/admin/slots").text)
r = post(a, f"/admin/slots/{ids[-1]}/delete", "/admin/slots")
rec("SV-17", "Admin removes an available slot", "Slot removed", f"HTTP {r.status_code}; SV-99 rows: {a.get(B+'/admin/slots').text.count('SV-99')}", "SV-99" not in a.get(B + "/admin/slots").text)

r = post(c1, "/logout", "/dashboard")
r = c1.get(B + "/dashboard", allow_redirects=False)
rec("SV-18", "Logout ends the session", "Dashboard redirects to login", f"HTTP {r.status_code} to {r.headers.get('Location')}", r.status_code == 302)

r = requests.post(B + "/login", data={"email": "admin@vps.com", "password": "admin123"})
rec("SV-19", "POST without CSRF token", "Request rejected (400)", f"HTTP {r.status_code}", r.status_code == 400)

c3, r = login("sys1@test.com", "wrongpass")
rec("SV-20", "Login with wrong password", "Error message, stays on login", f"HTTP {r.status_code}", "Invalid email or password" in r.text)

json.dump(results, open("/home/claude/sysval.json", "w"), indent=1)
for x in results: print(x["id"], x["status"], x["actual"])
print(sum(x["status"]=="Pass" for x in results), "/", len(results))
