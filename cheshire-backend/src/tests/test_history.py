import sqlite3
import pytest
from knowledge_base.history import Event, EventType, SqliteEventRepository

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()

@pytest.fixture
def repo(db_conn):
    return SqliteEventRepository(db_conn)

def test_save_and_get_recent_events(repo):
    session_id = "session_1"
    event1 = Event(session_id=session_id, event_type=EventType.USER_MESSAGE, content="Hello")
    event2 = Event(session_id=session_id, event_type=EventType.RESPONSE, content="Hi there")
    
    repo.save(event1)
    repo.save(event2)
    
    recent = repo.get_recent(session_id, 10)
    assert len(recent) == 2
    assert recent[0].content == "Hi there"
    assert recent[0].event_type == EventType.RESPONSE
    assert recent[1].content == "Hello"
    assert recent[1].event_type == EventType.USER_MESSAGE

def test_get_event_by_id(repo):
    session_id = "session_2"
    event = Event(session_id=session_id, event_type=EventType.USER_MESSAGE, content="Check ID")
    repo.save(event)
    
    # Get the ID of the inserted event
    recent = repo.get_recent(session_id, 1)
    event_id = recent[0].event_id
    
    fetched = repo.get_event(event_id)
    assert fetched is not None
    assert fetched.content == "Check ID"
    assert fetched.session_id == session_id

def test_ref_event_id(repo):
    session_id = "session_3"
    parent = Event(session_id=session_id, event_type=EventType.USER_MESSAGE, content="Question")
    repo.save(parent)
    
    parent_id = repo.get_recent(session_id, 1)[0].event_id
    
    child = Event(session_id=session_id, event_type=EventType.RESPONSE, content="Answer", ref_event_id=parent_id)
    repo.save(child)
    
    recent = repo.get_recent(session_id, 2)
    assert recent[0].ref_event_id == parent_id
