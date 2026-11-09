from sqlmodel import Session


def test_connections_run_without_jit(session: Session):
    assert session.connection().exec_driver_sql("show jit").scalar() == "off"
