# # actions/rabbitmq_producer.py
# import os
# import json
# import pika
# from typing import Optional, Dict, Any

# # Environment Loading
# from dotenv import load_dotenv
# load_dotenv()

# # --- Configuration ---
# RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
# RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "rasa_events")

# # --- Lazy Initialization of RabbitMQ Connection & Channel ---
# _CONNECTION: Optional[pika.BlockingConnection] = None
# _CHANNEL: Optional[pika.channel.Channel] = None

# def _get_channel() -> Optional[pika.channel.Channel]:
#     """
#     Initializes and returns a singleton RabbitMQ channel.
#     Also ensures the queue exists. Returns None if connection fails.
#     """
#     global _CONNECTION, _CHANNEL
#     if _CHANNEL and _CHANNEL.is_open:
#         return _CHANNEL

#     try:
#         print(f"[LOG] Attempting to connect to RabbitMQ at {RABBITMQ_URL}...")
#         params = pika.URLParameters(RABBITMQ_URL)
#         _CONNECTION = pika.BlockingConnection(params)
#         _CHANNEL = _CONNECTION.channel()

#         # Declare a durable queue to ensure it survives broker restarts
#         _CHANNEL.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
#         print("✅ Successfully connected to RabbitMQ and ensured queue exists.")
#         return _CHANNEL
#     except pika.exceptions.AMQPConnectionError as e:
#         print(f"⚠️ Warning: Could not connect to RabbitMQ. Event publishing will be disabled. Error: {e}")
#         _CONNECTION, _CHANNEL = None, None
#         return None

# def send_event_to_rabbitmq(event_data: Dict[str, Any]):
#     """
#     Sends a dictionary payload as a persistent JSON message to the configured RabbitMQ queue.
#     """
#     channel = _get_channel()
#     if not channel:
#         print("[LOG] RabbitMQ channel not available. Skipping event publishing.")
#         return

#     try:
#         message_body = json.dumps(event_data)
#         print(f"[LOG] Publishing event to RabbitMQ queue '{RABBITMQ_QUEUE}'...")
        
#         channel.basic_publish(
#             exchange='',  # Default exchange
#             routing_key=RABBITMQ_QUEUE,
#             body=message_body,
#             properties=pika.BasicProperties(
#                 delivery_mode=2,  # make message persistent
#             ))
#         print("[LOG] Event successfully published to RabbitMQ.")
#     except Exception as e:
#         print(f"[ERROR] Failed to publish event to RabbitMQ. Error: {e}")
#         # In case of channel issues, reset to force reconnection on next call
#         global _CHANNEL, _CONNECTION
#         _CHANNEL, _CONNECTION = None, None