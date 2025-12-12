#!/bin/bash
# Phase 5: Automated Learning Loop

echo "🚀 Starting Autonomous Training Loop..."
echo "Press Ctrl+C to stop."

# Loop indefinitely
while true
do
    echo ""
    echo "=================================================="
    echo "🔄 New Iteration..."
    echo "=================================================="
    
    # 1. The Brain: Generate Proposal
    echo "🧠 Agent Thinking..."
    # Ensure env vars are loaded (if not handled by python script loading .env)
    # But python script doesn't load .env automatically unless we use python-dotenv or source it here.
    # Let's source it here to be safe.
    source quants-lab/.env.sh
    
    python3 quants-lab/phase5_learning_agent.py
    if [ $? -ne 0 ]; then
        echo "❌ Agent failed. Stopping loop."
        exit 1
    fi
    
    # 2. The Body: Execute Proposal
    echo "💪 Executor Acting..."
    # --force used because initial runs might have low confidence/safe defaults
    python3 hummingbot/scripts/execute_next_proposal.py --force --duration 600
    if [ $? -ne 0 ]; then
        echo "❌ Execution failed. Stopping loop."
        exit 1
    fi
    
    echo "✅ Iteration Complete."
    echo "Sleeping for 10 seconds..."
    sleep 10
done

echo ""
echo "🎉 Training Session Complete!"
