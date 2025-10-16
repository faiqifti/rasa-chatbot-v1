# actions/test_rabbitmq_producer.py
import time
from .rabbitmq_producer import send_event_to_rabbitmq

# --- Main test execution ---
if __name__ == "__main__":
    print("\n--- Testing RabbitMQ Producer Module ---")
    
    # 1. Create a sample event payload, just like Rasa would
    test_event = {
        "user_question": "test: what is the transfer limit?",
        "retrieved_answer": "The daily transfer limit is Rp25 million.",
        "source": "kb/transfer.md",
        "score": 0.99,
        "sender_id": "test_sender_01",
        "timestamp": time.time()
    }
    
    print("\nAttempting to send a test event...")
    
    # 2. Call the function from your module
    # This will trigger the connection and attempt to send the message.
    send_event_to_rabbitmq(test_event)
    
    print("\n--- Test complete ---")
    print("Check your RabbitMQ Dashboard now to see if the message arrived in the 'rasa_events' queue.")