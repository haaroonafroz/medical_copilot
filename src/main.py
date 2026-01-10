import os
import sys
import traceback
from dotenv import load_dotenv

# Ensure src is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load env before imports that use settings
load_dotenv()

from langchain_core.messages import HumanMessage
from agents.graph import agent_graph

def main():
    print("=== Medical Co-Pilot (CLI) ===")
    print("Type 'quit' to exit.")
    print("Try asking: 'Review patient test-patient-001'")

    # Initialize state
    chat_history = []
    
    while True:
        user_input = input("\nUser: ")
        if user_input.lower() in ["quit", "exit"]:
            break
        
        # Create initial state
        initial_state = {
            "messages": chat_history + [HumanMessage(content=user_input)],
            "patient_id": None
        }
        
        print("\n--- Agent Thinking ---")
        try:
            # Stream the graph execution
            for event in agent_graph.stream(initial_state):
                for key, value in event.items():
                    print(f"Finished Node: {key}")

            final_state = agent_graph.invoke(initial_state)
            
            # Display Final Response
            bot_response = final_state['messages'][-1].content
            print(f"\nAssistant:\n{bot_response}")
            
            # Update history
            chat_history.append(HumanMessage(content=user_input))
            chat_history.append(final_state['messages'][-1])
            
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()

