#!/usr/bin/env python3
"""Create a simple test RFP file for testing the analyzer."""

import pandas as pd

def create_test_rfp():
    """Create a test RFP Excel file with questions."""
    
    # Test questions for RFP response generation
    questions = [
        "Does your platform support real-time data processing?",
        "What security certifications do you have?", 
        "Can you integrate with our existing CRM system?",
        "What is your uptime guarantee?",
        "Do you provide 24/7 customer support?",
        "What is your data backup and recovery process?",
        "Can you handle high-volume transactions?",
        "What training do you provide for new users?",
        "Do you support single sign-on (SSO)?",
        "What is your pricing model?"
    ]
    
    # Create DataFrame
    df = pd.DataFrame({
        'Question': questions
    })
    
    # Save to Excel file
    output_file = './test_rfp_simple.xlsx'
    df.to_excel(output_file, index=False)
    
    print(f"✅ Created test RFP file: {output_file}")
    print(f"📊 Contains {len(questions)} questions")
    
    return output_file

if __name__ == "__main__":
    create_test_rfp()
