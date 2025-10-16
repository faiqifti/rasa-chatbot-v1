# actions/rabbitmq_producer.py
import os
import json
import pika
import time
from typing import Optional, Dict, Any
from enum import Enum

# Environment Loading
from dotenv import load_dotenv
load_dotenv()

# --- Configuration ---
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

# Define different queues for different types of events
class QueueType(Enum):
    TOTAL_INCOMING = "chatbot_total_incoming"
    READY = "chatbot_ready"
    PROCESSING = "chatbot_processing" 
    SUCCESS = "chatbot_success"
    FAILED = "chatbot_failed"
    DELIVERED = "chatbot_delivered"
    # Additional queues for comprehensive monitoring
    ON_HOLD = "chatbot_on_hold"
    ERROR = "chatbot_error"
    METRICS = "chatbot_metrics"

# --- Lazy Initialization of RabbitMQ Connection & Channel ---
_CONNECTION: Optional[pika.BlockingConnection] = None
_CHANNEL: Optional[pika.channel.Channel] = None
_LAST_CONNECTION_ATTEMPT: float = 0
_CONNECTION_COOLDOWN: float = 5.0  # seconds

def _get_channel() -> Optional[pika.channel.Channel]:
    """
    Enhanced connection management with auto-recovery
    """
    global _CONNECTION, _CHANNEL
    
    # First, check if we have a working channel
    if _CHANNEL and _CHANNEL.is_open:
        try:
            # Test the channel by doing a simple operation
            _CHANNEL.queue_declare(queue='chatbot_total_incoming', passive=True)
            return _CHANNEL
        except (pika.exceptions.ChannelClosed, pika.exceptions.ConnectionClosed, 
                pika.exceptions.StreamLostError, Exception) as e:
            print(f"🔄 [RABBITMQ] Channel test failed: {e}. Reconnecting...")
            _CHANNEL, _CONNECTION = None, None
    
    # If no channel or channel is broken, create new connection
    try:
        print(f"🔗 [RABBITMQ] Establishing new connection to {RABBITMQ_URL}...")
        
        # Close existing connection if any
        if _CONNECTION and _CONNECTION.is_open:
            try:
                _CONNECTION.close()
            except:
                pass
        
        # Create new connection with robust settings
        params = pika.URLParameters(RABBITMQ_URL)
        params.heartbeat = 600  # 10 minutes
        params.blocked_connection_timeout = 300  # 5 minutes
        params.connection_attempts = 3
        params.retry_delay = 5
        
        _CONNECTION = pika.BlockingConnection(params)
        _CHANNEL = _CONNECTION.channel()

        # Declare all queues to ensure they exist
        for queue in QueueType:
            _CHANNEL.queue_declare(
                queue=queue.value, 
                durable=True,
                arguments={'x-queue-mode': 'lazy'}
            )
        
        print("✅ [RABBITMQ] New connection established and queues declared")
        return _CHANNEL
        
    except Exception as e:
        print(f"❌ [RABBITMQ] Connection failed: {e}")
        _CONNECTION, _CHANNEL = None, None
        return None

    # try:
    #     print(f"[LOG] Attempting to connect to RabbitMQ at {RABBITMQ_URL}...")
    #     params = pika.URLParameters(RABBITMQ_URL)
    #     _CONNECTION = pika.BlockingConnection(params)
    #     _CHANNEL = _CONNECTION.channel()

    #     # Declare all required queues as durable to ensure they survive broker restarts
    #     for queue in QueueType:
    #         _CHANNEL.queue_declare(
    #             queue=queue.value, 
    #             durable=True,
    #             arguments={
    #                 'x-queue-mode': 'lazy'  # Store messages on disk more aggressively
    #             }
    #         )
        
    #     print("✅ Successfully connected to RabbitMQ and ensured all queues exist.")
    #     return _CHANNEL
    # except pika.exceptions.AMQPConnectionError as e:
    #     print(f"⚠️ Warning: Could not connect to RabbitMQ. Event publishing will be disabled. Error: {e}")
    #     _CONNECTION, _CHANNEL = None, None
    #     return None

# Tambahkan function untuk test connection
def test_connection():
    """Test RabbitMQ connection and return status"""
    channel = _get_channel()
    if channel:
        print("✅ [RABBITMQ] Connection test: SUCCESS")
        return True
    else:
        print("❌ [RABBITMQ] Connection test: FAILED")
        return False

def send_event_to_rabbitmq(event_data: Dict[str, Any], queue_type: QueueType):
    """
    Sends a dictionary payload as a persistent JSON message to the specified RabbitMQ queue.
    
    Args:
        event_data: Dictionary containing event information
        queue_type: Type of queue to send the event to (from QueueType enum)
    """
    channel = _get_channel()
    if not channel:
        print("[LOG] RabbitMQ channel not available. Skipping event publishing.")
        return False

    try:
        # Add timestamp and event type to the payload
        enhanced_data = {
            **event_data,
            "timestamp": event_data.get("timestamp") or json.dumps({"timestamp": "placeholder"}),  # Use ISO format
            "event_type": queue_type.value,
            "version": "1.0"
        }
        
        message_body = json.dumps(enhanced_data)
        queue_name = queue_type.value
        
        print(f"[LOG] Publishing {queue_type.name} event to RabbitMQ queue '{queue_name}'...")
        
        channel.basic_publish(
            exchange='',  # Default exchange
            routing_key=queue_name,
            body=message_body,
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
                content_type='application/json',
            ))
        print(f"✅ {queue_type.name} event successfully published to RabbitMQ.")
        return True
    except Exception as e:
        print(f"❌ [ERROR] Failed to publish {queue_type.name} event to RabbitMQ. Error: {e}")
        # In case of channel issues, reset to force reconnection on next call
        global _CHANNEL, _CONNECTION
        _CHANNEL, _CONNECTION = None, None
        return False

# --- Convenience functions for different event types ---

# safe wrapper
def _safe_publish(queue_type: QueueType, event_data: Dict[str, Any]) -> bool:
    """
    Safe wrapper for publishing events with automatic retry
    """
    max_retries = 2
    for attempt in range(max_retries):
        channel = _get_channel()
        if not channel:
            print(f"❌ [SAFE_PUBLISH] No channel available (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait before retry
                continue
            return False

        try:
            # Enhance event data with timestamp
            enhanced_data = {
                **event_data,
                "timestamp": time.time(),
                "event_type": queue_type.value,
                "version": "1.0",
                "attempt": attempt + 1
            }
            
            message_body = json.dumps(enhanced_data)
            queue_name = queue_type.value
            
            channel.basic_publish(
                exchange='',
                routing_key=queue_name,
                body=message_body,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent
                    content_type='application/json',
                )
            )
            
            if attempt > 0:
                print(f"✅ [SAFE_PUBLISH] Success on retry {attempt + 1} for {queue_type.name}")
            else:
                print(f"✅ [SAFE_PUBLISH] Published to {queue_type.name}")
                
            return True
            
        except (pika.exceptions.ChannelClosed, pika.exceptions.ConnectionClosed, 
                pika.exceptions.StreamLostError) as e:
            print(f"🔄 [SAFE_PUBLISH] Channel error on attempt {attempt + 1}: {e}")
            # Reset connection for retry
            global _CHANNEL, _CONNECTION
            _CHANNEL, _CONNECTION = None, None
            
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait before retry
                continue
                
        except Exception as e:
            print(f"❌ [SAFE_PUBLISH] Unexpected error: {e}")
            return False
    
    return False

# def track_incoming_message(session_id: str, message: str, user_id: str, metadata: Dict[str, Any] = None):
#     """Track when a new message comes in from user"""
#     event_data = {
#         "session_id": session_id,
#         "user_message": message,
#         "user_id": user_id,
#         "action": "message_received",
#         "metadata": metadata or {}
#     }
#     return send_event_to_rabbitmq(event_data, QueueType.TOTAL_INCOMING)

# def track_ready_message(session_id: str, message_id: str, metadata: Dict[str, Any] = None):
#     """Track when a message is ready for processing"""
#     event_data = {
#         "session_id": session_id,
#         "message_id": message_id,
#         "action": "message_ready",
#         "status": "ready",
#         "metadata": metadata or {}
#     }
#     return send_event_to_rabbitmq(event_data, QueueType.READY)

def track_incoming_message(session_id: str, message: str, user_id: str, metadata: Dict[str, Any] = None):
    """Track when a new message comes in from user"""
    event_data = {
        "session_id": session_id,
        "user_message": message,
        "user_id": user_id,
        "action": "message_received",
        "metadata": metadata or {}
    }
    return _safe_publish(QueueType.TOTAL_INCOMING, event_data)

def track_ready_message(session_id: str, message_id: str, metadata: Dict[str, Any] = None):
    """Track when a message is ready for processing"""
    event_data = {
        "session_id": session_id,
        "message_id": message_id,
        "action": "message_ready",
        "status": "ready",
        "metadata": metadata or {}
    }
    return _safe_publish(QueueType.READY, event_data)

def track_processing_message(session_id: str, message_id: str, processor: str, metadata: Dict[str, Any] = None):
    """Track when a message starts being processed"""
    event_data = {
        "session_id": session_id,
        "message_id": message_id,
        "processor": processor,
        "action": "processing_started",
        "status": "processing",
        "metadata": metadata or {}
    }
    return _safe_publish(QueueType.PROCESSING, event_data)

def track_success_response(session_id: str, message_id: str, response: str, processing_time: float = None):
    """Track successful response generation"""
    event_data = {
        "session_id": session_id,
        "message_id": message_id,
        "response": response,
        "action": "response_success",
        "status": "success",
        "processing_time_seconds": processing_time,
        "metadata": {}
    }
    return _safe_publish(QueueType.SUCCESS, event_data)

def track_failed_response(session_id: str, message_id: str, error: str, error_type: str = None):
    """Track failed response generation"""
    event_data = {
        "session_id": session_id,
        "message_id": message_id,
        "error": error,
        "error_type": error_type,
        "action": "response_failed",
        "status": "failed",
        "metadata": {}
    }
    return _safe_publish(QueueType.FAILED, event_data)

def track_delivered_message(session_id: str, message_id: str, delivery_channel: str):
    """Track when a response is delivered to user"""
    event_data = {
        "session_id": session_id,
        "message_id": message_id,
        "delivery_channel": delivery_channel,
        "action": "message_delivered",
        "status": "delivered",
        "metadata": {}
    }
    return _safe_publish(QueueType.DELIVERED, event_data)

def track_on_hold_message(session_id: str, message_id: str, reason: str, metadata: Dict[str, Any] = None):
    """Track when a message is put on hold"""
    event_data = {
        "session_id": session_id,
        "message_id": message_id,
        "reason": reason,
        "action": "message_on_hold",
        "status": "on_hold",
        "metadata": metadata or {}
    }
    return _safe_publish(QueueType.ON_HOLD, event_data)

def track_error(session_id: str, error: str, component: str, traceback: str = None):
    """Track general errors"""
    event_data = {
        "session_id": session_id,
        "error": error,
        "component": component,
        "traceback": traceback,
        "action": "system_error",
        "severity": "error",
        "metadata": {}
    }
    return _safe_publish(QueueType.ERROR, event_data)

def track_metrics(metric_name: str, value: float, tags: Dict[str, str] = None):
    """Track custom metrics"""
    event_data = {
        "metric_name": metric_name,
        "value": value,
        "tags": tags or {},
        "action": "metric_recorded",
        "type": "metric",
        "metadata": {}
    }
    return _safe_publish(QueueType.METRICS, event_data)

# --- Utility function to get queue statistics ---
def get_queue_stats():
    """
    Returns basic information about all monitoring queues.
    Note: This requires RabbitMQ Management Plugin to be enabled.
    """
    # This is a simplified version - in production you might want to use the HTTP API
    channel = _get_channel()
    if not channel:
        return None
    
    stats = {}
    try:
        for queue in QueueType:
            method_frame = channel.queue_declare(queue=queue.value, passive=True)
            stats[queue.value] = {
                'messages_ready': method_frame.method.message_count,
                'consumers': method_frame.method.consumer_count
            }
        return stats
    except Exception as e:
        print(f"❌ [ERROR] Failed to get queue stats: {e}")
        return None

# --- Cleanup function ---
def close_connection():
    """Close the RabbitMQ connection gracefully"""
    global _CHANNEL, _CONNECTION
    if _CHANNEL and _CHANNEL.is_open:
        _CHANNEL.close()
    if _CONNECTION and _CONNECTION.is_open:
        _CONNECTION.close()
    _CHANNEL, _CONNECTION = None, None
    print("✅ RabbitMQ connection closed.")