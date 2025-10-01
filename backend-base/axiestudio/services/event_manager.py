# -*- coding: utf-8 -*-
"""
📡 EVENT MANAGER SERVICE
Manages events and event handling throughout the AxieStudio system
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from axiestudio.logging import logger


class EventType(Enum):
    """Event types for the system"""
    FLOW_START = "flow_start"
    FLOW_COMPLETE = "flow_complete"
    FLOW_ERROR = "flow_error"
    COMPONENT_START = "component_start"
    COMPONENT_COMPLETE = "component_complete"
    COMPONENT_ERROR = "component_error"
    USER_ACTION = "user_action"
    SYSTEM_EVENT = "system_event"
    CUSTOM_EVENT = "custom_event"


@dataclass
class Event:
    """Event data structure"""
    event_type: EventType
    event_id: str
    timestamp: datetime
    data: Dict[str, Any]
    source: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class EventManager:
    """
    📡 Event Manager
    
    Manages event publishing, subscription, and handling throughout the system.
    Provides a centralized way to handle events and notifications.
    """
    
    def __init__(self):
        """Initialize the event manager"""
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._event_history: List[Event] = []
        self._max_history_size = 1000
        self._running = False
        
    async def start(self) -> None:
        """Start the event manager"""
        self._running = True
        logger.info("Event manager started")
    
    async def stop(self) -> None:
        """Stop the event manager"""
        self._running = False
        logger.info("Event manager stopped")
    
    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """
        Subscribe to an event type
        
        Args:
            event_type: Type of event to subscribe to
            callback: Function to call when event occurs
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type.value}")
    
    def unsubscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        """
        Unsubscribe from an event type
        
        Args:
            event_type: Type of event to unsubscribe from
            callback: Function to remove from subscribers
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
                logger.debug(f"Unsubscribed from {event_type.value}")
            except ValueError:
                logger.warning(f"Callback not found for {event_type.value}")
    
    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers
        
        Args:
            event: Event to publish
        """
        if not self._running:
            logger.warning("Event manager not running, event not published")
            return
        
        # Add to history
        self._add_to_history(event)
        
        # Notify subscribers
        if event.event_type in self._subscribers:
            for callback in self._subscribers[event.event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")
        
        logger.debug(f"Published event: {event.event_type.value}")
    
    async def publish_event(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> None:
        """
        Convenience method to publish an event
        
        Args:
            event_type: Type of event
            data: Event data
            source: Source of the event
            session_id: Session ID if applicable
            user_id: User ID if applicable
        """
        import uuid
        
        event = Event(
            event_type=event_type,
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            data=data,
            source=source,
            session_id=session_id,
            user_id=user_id
        )
        
        await self.publish(event)
    
    def _add_to_history(self, event: Event) -> None:
        """Add event to history with size limit"""
        self._event_history.append(event)
        
        # Maintain history size limit
        if len(self._event_history) > self._max_history_size:
            self._event_history = self._event_history[-self._max_history_size:]
    
    def get_event_history(
        self,
        event_type: Optional[EventType] = None,
        session_id: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Event]:
        """
        Get event history with optional filtering
        
        Args:
            event_type: Filter by event type
            session_id: Filter by session ID
            limit: Limit number of events returned
            
        Returns:
            List of events matching criteria
        """
        events = self._event_history
        
        # Filter by event type
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        # Filter by session ID
        if session_id:
            events = [e for e in events if e.session_id == session_id]
        
        # Apply limit
        if limit:
            events = events[-limit:]
        
        return events
    
    def get_subscriber_count(self, event_type: EventType) -> int:
        """Get number of subscribers for an event type"""
        return len(self._subscribers.get(event_type, []))
    
    def clear_history(self) -> None:
        """Clear event history"""
        self._event_history.clear()
        logger.info("Event history cleared")
    
    def is_running(self) -> bool:
        """Check if event manager is running"""
        return self._running


# Global event manager instance
_event_manager: Optional[EventManager] = None


def get_event_manager() -> EventManager:
    """Get the global event manager instance"""
    global _event_manager
    if _event_manager is None:
        _event_manager = EventManager()
    return _event_manager


async def start_event_manager() -> EventManager:
    """Start the global event manager"""
    manager = get_event_manager()
    await manager.start()
    return manager


async def stop_event_manager() -> None:
    """Stop the global event manager"""
    global _event_manager
    if _event_manager:
        await _event_manager.stop()


# Convenience functions
async def publish_flow_start(session_id: str, flow_id: str, **kwargs) -> None:
    """Publish flow start event"""
    manager = get_event_manager()
    await manager.publish_event(
        EventType.FLOW_START,
        {"flow_id": flow_id, **kwargs},
        session_id=session_id
    )


async def publish_flow_complete(session_id: str, flow_id: str, result: Any, **kwargs) -> None:
    """Publish flow complete event"""
    manager = get_event_manager()
    await manager.publish_event(
        EventType.FLOW_COMPLETE,
        {"flow_id": flow_id, "result": result, **kwargs},
        session_id=session_id
    )


async def publish_flow_error(session_id: str, flow_id: str, error: str, **kwargs) -> None:
    """Publish flow error event"""
    manager = get_event_manager()
    await manager.publish_event(
        EventType.FLOW_ERROR,
        {"flow_id": flow_id, "error": error, **kwargs},
        session_id=session_id
    )


# Export main classes and functions
__all__ = [
    "EventManager",
    "Event", 
    "EventType",
    "get_event_manager",
    "start_event_manager",
    "stop_event_manager",
    "publish_flow_start",
    "publish_flow_complete", 
    "publish_flow_error"
]
