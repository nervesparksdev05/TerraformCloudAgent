"""
Test script for README-driven deployment flow.

Tests:
1. GitHub service - fetch README
2. README analyzer - extract requirements
3. Form generator - create dynamic form
4. Conversation manager - end-to-end flow
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.github_service import get_github_service
from app.services.readme_analyzer import get_readme_analyzer
from app.services.form_generator import get_form_generator


async def test_github_service():
    """Test GitHub README fetching."""
    print("\n" + "="*60)
    print("TEST 1: GitHub Service - Fetch README")
    print("="*60)
    
    github_service = get_github_service()
    
    # Test with a well-known public repo
    test_repos = [
        "vercel/next.js",
        "fastapi/fastapi",
    ]
    
    for repo_url in test_repos:
        try:
            print(f"\nFetching README from: {repo_url}")
            readme_data = await github_service.fetch_readme(repo_url)
            
            print(f"✅ Success!")
            print(f"  - Filename: {readme_data['filename']}")
            print(f"  - Size: {readme_data['size']} bytes")
            print(f"  - Content preview: {readme_data['content'][:200]}...")
            
        except Exception as e:
            print(f"❌ Failed: {e}")
    
    await github_service.close()


async def test_readme_analyzer():
    """Test README analysis."""
    print("\n" + "="*60)
    print("TEST 2: README Analyzer - Extract Requirements")
    print("="*60)
    
    github_service = get_github_service()
    readme_analyzer = get_readme_analyzer()
    
    # Fetch a README
    repo_url = "fastapi/fastapi"
    print(f"\nAnalyzing README from: {repo_url}")
    
    try:
        readme_data = await github_service.fetch_readme(repo_url)
        analysis = await readme_analyzer.analyze(readme_data['content'], repo_url)
        
        print(f"\n✅ Analysis complete!")
        print(f"  - Language: {analysis.get('tech_stack', {}).get('language')}")
        print(f"  - Framework: {analysis.get('tech_stack', {}).get('framework')}")
        print(f"  - Workload: {analysis.get('workload_type')}")
        print(f"  - Ports: {analysis.get('ports')}")
        print(f"  - Dependencies: {len(analysis.get('dependencies', []))} found")
        print(f"  - Confidence: {analysis.get('confidence', 0):.0%}")
        print(f"  - Reasoning: {analysis.get('reasoning', '')[:100]}...")
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
    
    await github_service.close()


async def test_form_generator():
    """Test form generation."""
    print("\n" + "="*60)
    print("TEST 3: Form Generator - Create Dynamic Form")
    print("="*60)
    
    github_service = get_github_service()
    readme_analyzer = get_readme_analyzer()
    form_generator = get_form_generator()
    
    repo_url = "fastapi/fastapi"
    print(f"\nGenerating form for: {repo_url}")
    
    try:
        # Get README and analyze
        readme_data = await github_service.fetch_readme(repo_url)
        analysis = await readme_analyzer.analyze(readme_data['content'], repo_url)
        
        # Generate form
        form_data = form_generator.generate_form(analysis)
        
        print(f"\n✅ Form generated!")
        print(f"  - Pre-filled fields: {len(form_data['pre_filled'])}")
        print(f"  - Required fields: {len(form_data['required_fields'])}")
        print(f"  - Optional fields: {len(form_data['optional_fields'])}")
        
        print(f"\n  Pre-filled parameters:")
        for key, value in list(form_data['pre_filled'].items())[:3]:
            print(f"    • {key}: {value}")
        
        print(f"\n  Required fields:")
        for field in form_data['required_fields'][:3]:
            print(f"    • {field['label']} ({field['type']})")
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()
    
    await github_service.close()


async def test_end_to_end():
    """Test complete end-to-end flow."""
    print("\n" + "="*60)
    print("TEST 4: End-to-End - Complete README-Driven Flow")
    print("="*60)
    
    from app.services.conversation_manager import ConversationManager
    
    conv_manager = ConversationManager()
    
    repo_url = "fastapi/fastapi"
    print(f"\nTesting complete flow for: {repo_url}")
    
    try:
        # Step 1: Create session
        print("\n1. Creating session...")
        session_data = conv_manager.create_session(
            github_url=repo_url,
            provider="aws"
        )
        session_id = session_data["session_id"]
        print(f"   ✅ Session created: {session_id}")
        
        # Step 2: Analyze README
        print("\n2. Analyzing README...")
        analysis_response = await conv_manager.analyze_readme(session_id)
        print(f"   ✅ Analysis complete")
        print(f"   - Bot response preview: {analysis_response.bot_response[:150]}...")
        
        # Step 3: Submit form (simulate user input)
        print("\n3. Submitting form...")
        user_input = {
            "cloud_provider": "aws",
            "region": "us-east-1",
            "instance_count": 2,
            "instance_type": "t3.small"
        }
        form_response = await conv_manager.process_form_input(session_id, user_input)
        print(f"   ✅ Form submitted")
        print(f"   - Session complete: {form_response.is_complete}")
        
        # Step 4: Build Terraform request
        print("\n4. Building Terraform request...")
        terraform_request = conv_manager.build_terraform_request(session_id)
        print(f"   ✅ Request built")
        print(f"   - Provider: {terraform_request['cloud_provider']}")
        print(f"   - Instance type: {terraform_request['instance_type']}")
        print(f"   - Instance count: {terraform_request['instance_count']}")
        print(f"   - Ports: {terraform_request['ports']}")
        
        print(f"\n🎉 End-to-end test PASSED!")
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("README-DRIVEN DEPLOYMENT - TEST SUITE")
    print("="*60)
    
    await test_github_service()
    await test_readme_analyzer()
    await test_form_generator()
    await test_end_to_end()
    
    print("\n" + "="*60)
    print("ALL TESTS COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
