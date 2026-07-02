import pytest

from app import create_app
from app.extensions import db
from app.models import Activity, Project, User


@pytest.fixture
def app(tmp_path):
    app = create_app("testing")
    app.config["BACKUP_DIR"] = str(tmp_path / "backups")
    with app.app_context():
        db.create_all()
        admin = User(username="admin", role="Administrador")
        admin.set_password("secret123")
        emp = User(username="emp", role="Empleado")
        emp.set_password("secret123")
        db.session.add_all([admin, emp])
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, user="admin", pw="secret123"):
    return client.post("/login", data={"username": user, "password": pw},
                       follow_redirects=True)


def make_sheet(app):
    with app.app_context():
        p = Project(created_by="admin", modified_by="admin")
        db.session.add(p)
        db.session.commit()
        return p.id


# --- seguridad básica ------------------------------------------------------- #
def test_passwords_are_hashed(app):
    with app.app_context():
        u = User.query.filter_by(username="admin").first()
        assert u.password_hash != "secret123"
        assert u.check_password("secret123")


def test_login_required_redirects(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_login_failure(client):
    bad = client.post("/login", data={"username": "admin", "password": "no"},
                      follow_redirects=True)
    assert "incorrectos".encode() in bad.data


def test_security_headers(client):
    r = client.get("/login")
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in r.headers


def test_secret_required_in_production(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_app("production")


# --- espacio compartido ----------------------------------------------------- #
def test_any_user_sees_and_edits_shared_sheets(app, client):
    pid = make_sheet(app)
    # un empleado distinto al creador puede abrir y guardar
    login(client, "emp")
    assert client.get(f"/hoja/{pid}").status_code == 200
    r = client.post(f"/hoja/{pid}/api/preexa/save",
                    json={"payload": {"levels": [{"nominal": "100", "replicates": ["100"]}]},
                          "base_version": 0})
    assert r.get_json()["saved"] is True


def test_creating_sheet_logs_activity(app, client):
    login(client)
    client.post("/hoja/nueva", follow_redirects=True)
    with app.app_context():
        assert Activity.query.filter(Activity.category == "sheet").count() >= 1


# --- presencia -------------------------------------------------------------- #
def test_presence_lists_online_user(app, client):
    login(client)
    data = client.get("/api/presence").get_json()
    assert data["you"] == "admin"
    assert any(u["username"] == "admin" for u in data["online"])


def test_activity_page_visible_to_all(app, client):
    login(client, "emp")
    assert client.get("/actividad").status_code == 200


# --- detección de conflictos ------------------------------------------------ #
def test_conflict_detection(app, client):
    pid = make_sheet(app)
    login(client)
    first = client.post(f"/hoja/{pid}/api/preexa/save",
                        json={"payload": {"a": 1}, "base_version": 0}).get_json()
    new_version = first["version"]
    # guardar con una versión vieja debe chocar
    stale = client.post(f"/hoja/{pid}/api/preexa/save",
                        json={"payload": {"a": 2}, "base_version": new_version - 1000})
    assert stale.status_code == 409
    assert stale.get_json()["conflict"] is True
    # forzando, se sobrescribe
    forced = client.post(f"/hoja/{pid}/api/preexa/save",
                        json={"payload": {"a": 3}, "base_version": 0, "force": True})
    assert forced.get_json()["saved"] is True


# --- cálculo (servidor) ----------------------------------------------------- #
def test_compute_stats_api(app, client):
    pid = make_sheet(app)
    login(client)
    payload = {"limits": {"cv": 15, "dev": 15, "cv_lic": 20, "dev_lic": 20},
               "levels": [{"nominal": "100", "replicates": ["100", "102", "98", "101", "99"]}]}
    data = client.post(f"/hoja/{pid}/api/preexa/compute", json=payload).get_json()
    assert data["levels"][0]["verdict"] == "CUMPLE"


def test_compute_curve_api(app, client):
    pid = make_sheet(app)
    login(client)
    levels = [{"nominal": n, "response": n * 2 + 1} for n in (10, 50, 100, 200, 400)]
    reg = client.post(f"/hoja/{pid}/api/curva/compute",
                      json={"weight": "1", "limits": {"r": 0.99, "error": 15}, "levels": levels}
                      ).get_json()["regression"]
    assert abs(reg["slope"] - 2.0) < 1e-6


# --- usuarios y respaldos (sólo admin) -------------------------------------- #
def test_admin_only_pages(client):
    login(client, "emp")
    assert client.get("/usuarios").status_code == 403
    assert client.get("/respaldos").status_code == 403
    client.get("/logout")
    login(client, "admin")
    assert client.get("/usuarios").status_code == 200
    assert client.get("/respaldos").status_code == 200


def test_backup_create_and_list(app):
    from app.backup import create_backup, list_backups
    with app.app_context():
        path = create_backup()
        assert path.endswith(".json")
        assert len(list_backups()) == 1


def test_export_endpoint_downloads_json(app, client):
    login(client)
    r = client.get("/respaldos/exportar")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("Content-Disposition", "")
    assert b'"app": "valbio"' in r.data


# --- tabla personalizada (módulo libre) ------------------------------------- #
def test_free_table_page_and_compute(app, client):
    pid = make_sheet(app)
    login(client)
    assert client.get(f"/hoja/{pid}/modulo/tabla").status_code == 200
    free = {"tables": [{"title": "Pesos", "headers": ["Vial", "Peso"],
                        "rows": [["A", "10.0"], ["B", "10.2"], ["C", "9.8"]]}]}
    data = client.post(f"/hoja/{pid}/api/tabla/compute", json=free).get_json()
    col = data["tables"][0]["stats"][1]
    assert col["n"] == 3 and abs(col["mean"] - 10.0) < 1e-9


def test_free_table_save_and_reload(app, client):
    pid = make_sheet(app)
    login(client)
    free = {"tables": [{"title": "T", "headers": ["x"], "rows": [["1"], ["2"]]}]}
    r = client.post(f"/hoja/{pid}/api/tabla/save",
                    json={"payload": free, "base_version": 0})
    assert r.get_json()["saved"] is True
    page = client.get(f"/hoja/{pid}/modulo/tabla").get_data(as_text=True)
    assert '"headers"' in page and "Pesos" not in page


# --- informe HTML y PDF ----------------------------------------------------- #
def test_report_html_and_pdf(app, client):
    pid = make_sheet(app)
    login(client)
    payload = {"limits": {"cv": 15, "dev": 15, "cv_lic": 20, "dev_lic": 20},
               "levels": [{"nominal": "100", "replicates": ["100", "101", "99"]}]}
    client.post(f"/hoja/{pid}/api/preexa/save", json={"payload": payload, "base_version": 0})
    html = client.get(f"/hoja/{pid}/informe").get_data(as_text=True)
    assert client.get(f"/hoja/{pid}/informe").status_code == 200
    assert "Datos capturados" in html and "Resultados" in html
    pdf = client.get(f"/hoja/{pid}/informe.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["Content-Type"] == "application/pdf"
    assert pdf.data[:5] == b"%PDF-"


# --- importación de Excel --------------------------------------------------- #
def _xlsx_bytes():
    import io
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Datos"
    ws.append(["Vial", "Peso"])
    ws.append(["A", 10.1])
    ws.append(["B", 10.3])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_import_excel(app, client):
    pid = make_sheet(app)
    login(client)
    data = {"file": (_xlsx_bytes(), "muestra.xlsx")}
    r = client.post(f"/hoja/{pid}/api/import-excel", data=data,
                    content_type="multipart/form-data")
    out = r.get_json()
    assert r.status_code == 200
    assert out["tables"][0]["title"] == "Datos"
    assert out["tables"][0]["headers"] == ["Vial", "Peso"]
    assert out["tables"][0]["rows"][0] == ["A", "10.1"]
    # cuadrícula cruda para mapear a módulos estructurados (incluye la 1ª fila)
    assert out["tables"][0]["grid"][0] == ["Vial", "Peso"]
    assert out["tables"][0]["grid"][1] == ["A", "10.1"]


def test_import_excel_rejects_other_files(app, client):
    import io
    pid = make_sheet(app)
    login(client)
    data = {"file": (io.BytesIO(b"hello"), "notas.txt")}
    r = client.post(f"/hoja/{pid}/api/import-excel", data=data,
                    content_type="multipart/form-data")
    assert r.status_code == 400
