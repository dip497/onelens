#!/usr/bin/env python3
"""Create a sample RFP Excel file to show the expected format."""

import pandas as pd

def create_sample_rfp():
    """Create a sample RFP Excel file with the correct format."""
    
    # Sample questions that will be detected by the extraction logic
    questions = [
        "What is your company's experience in software development?",
        "How do you ensure data security and privacy?",
        "Can you provide 24/7 technical support?",
        "Do you offer cloud-based deployment options?",
        "Will you provide training for our staff?",
        "Are you compliant with GDPR regulations?",
        "Is your platform scalable for enterprise use?",
        "What is your typical implementation timeline?",
        "How do you handle system maintenance and updates?",
        "Can you integrate with our existing systems?"
    ]
    
    # Create DataFrame - the extraction logic looks for questions in any column
    df = pd.DataFrame({
        'Questions': questions  # This column name will be detected
    })
    
    # Save to Excel file
    output_file = './sample_rfp_format.xlsx'
    df.to_excel(output_file, index=False)
    
    print(f"✅ Created sample RFP file: {output_file}")
    print(f"📊 Contains {len(questions)} questions")
    print(f"📋 Column name: 'Questions'")
    print("\n🔍 Expected format:")
    print("- Questions should start with: What, How, Can, Do, Will, Are, Is")
    print("- Questions should be in a single column")
    print("- Each row should contain one question")
    
    return output_file

if __name__ == "__main__":
    create_sample_rfp()
