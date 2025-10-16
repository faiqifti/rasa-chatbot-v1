# test_actions.py
import sys
import os
import asyncio

# Add actions directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'actions'))

from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk import Tracker
from unittest.mock import Mock

# Import your action
from actions.actions import ActionRetrieveTop1

def test_action_with_rabbitmq():
    print("🧪 Testing ActionRetrieveTop1 with RabbitMQ...")
    
    # Mock dispatcher
    dispatcher = CollectingDispatcher()
    
    # Mock tracker
    tracker = Mock(spec=Tracker)
    tracker.latest_message = {"text": "biaya admin"}
    tracker.sender_id = "test-script-123"
    
    # Mock domain
    domain = {}
    
    # Create action instance
    action = ActionRetrieveTop1()
    
    # Run the action
    try:
        result = action.run(dispatcher, tracker, domain)
        print("✅ Action executed successfully!")
        print(f"📨 Dispatcher messages: {dispatcher.messages}")
        print(f"🔚 Action result: {result}")
    except Exception as e:
        print(f"❌ Action failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_action_with_rabbitmq()