import sqlite3
import pytest
from knowledge_base.session_manager import Session, SqliteSessionRepository

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()

@pytest.fixture
def repo(db_conn):
    return SqliteSessionRepository(db_conn)

def test_save_and_get_session(repo):
    session = Session(title="Test Session")
    repo.save_new_session(session)
    
    fetched = repo.get_session(session.session_id)
    assert fetched is not None
    assert fetched.title == "Test Session"
    assert fetched.session_id == session.session_id

def test_get_sessions_list(repo):
    s1 = Session(title="Session 1")
    s2 = Session(title="Session 2")
    repo.save_new_session(s1)
    repo.save_new_session(s2)
    
    sessions = repo.get_sessions()
    assert len(sessions) == 2
    titles = [s.title for s in sessions]
    assert "Session 1" in titles
    assert "Session 2" in titles

def test_get_session_with_title(repo):
    session = Session(title="Unique Title")
    repo.save_new_session(session)
    
    fetched = repo.get_session_with_title("Unique Title")
    assert fetched is not None
    assert fetched.session_id == session.session_id

def test_change_title(repo):
    session = Session(title="Original Title")
    repo.save_new_session(session)
    
    updated = repo.change_title(session.session_id, new_title="New Title")
    assert updated is not None
    assert updated.title == "New Title"
    
    fetched = repo.get_session(session.session_id)
    assert fetched.title == "New Title"

def test_change_title_non_existent(repo):
    updated = repo.change_title("non-existent-id", new_title="New Title")
    assert updated is None

def test_delete_session(repo):
    session = Session(title="To Be Deleted")
    repo.save_new_session(session)
    
    assert repo.get_session(session.session_id) is not None
    
    deleted = repo.delete_session(session.session_id)
    assert deleted is True
    
    assert repo.get_session(session.session_id) is None

def test_delete_session_non_existent(repo):
    deleted = repo.delete_session("non-existent-id")
    assert deleted is False
