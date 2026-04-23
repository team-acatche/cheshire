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

def test_get_last_event_timestamp(repo):
    session_id = "session_timestamp"
    
    # Case 1: No events
    assert repo.get_last_event_timestamp(session_id) is None
    
    # Case 2: One event
    ts1 = "2024-01-01 10:00:00"
    event1 = Event(session_id=session_id, event_type=EventType.USER_MESSAGE, content="First", timestamp=ts1)
    repo.save(event1)
    assert repo.get_last_event_timestamp(session_id) == ts1
    
    # Case 3: Multiple events
    ts2 = "2024-01-01 11:00:00"
    event2 = Event(session_id=session_id, event_type=EventType.RESPONSE, content="Second", timestamp=ts2)
    repo.save(event2)
    assert repo.get_last_event_timestamp(session_id) == ts2
    
    # Case 4: Event from another session
    other_session = "other_session"
    ts3 = "2024-01-01 12:00:00"
    event3 = Event(session_id=other_session, event_type=EventType.USER_MESSAGE, content="Other", timestamp=ts3)
    repo.save(event3)
    # Timestamp for session_timestamp should still be ts2
    assert repo.get_last_event_timestamp(session_id) == ts2
    # Timestamp for other_session should be ts3
    assert repo.get_last_event_timestamp(other_session) == ts3
