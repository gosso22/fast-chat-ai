#!/bin/bash

# Fast Chat AI - GitHub Push Commands
# Copy and paste these commands after creating your GitHub repository

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    Fast Chat AI - GitHub Push Script                        ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Before running this script:"
echo "1. Go to https://github.com/new"
echo "2. Create a new repository named 'fast-chat-ai' (or your preferred name)"
echo "3. DO NOT initialize with README, .gitignore, or license"
echo "4. Copy your repository URL"
echo ""
read -p "Enter your GitHub repository URL: " REPO_URL

if [ -z "$REPO_URL" ]; then
    echo "❌ Error: Repository URL is required"
    exit 1
fi

echo ""
echo "📡 Adding remote repository..."
git remote add origin "$REPO_URL"

echo "✅ Remote added successfully"
echo ""
echo "📤 Pushing to GitHub..."
git push -u origin master

if [ $? -eq 0 ]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                        ✅ PUSH SUCCESSFUL! ✅                                ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "🎉 Your repository is now on GitHub!"
    echo ""
    echo "📊 What was pushed:"
    echo "   • 20 meaningful commits"
    echo "   • ~100+ backend files"
    echo "   • ~50+ frontend files"
    echo "   • 20+ test suites"
    echo "   • Complete documentation"
    echo ""
    echo "🔗 View your repository:"
    echo "   $REPO_URL"
    echo ""
    echo "📚 Next steps:"
    echo "   1. Add repository description and topics on GitHub"
    echo "   2. Enable GitHub Actions (optional)"
    echo "   3. Set up branch protection (optional)"
    echo "   4. Share with your team!"
    echo ""
else
    echo ""
    echo "❌ Push failed. Common issues:"
    echo "   • Repository URL might be incorrect"
    echo "   • You might not have push access"
    echo "   • Repository might already have content"
    echo ""
    echo "To fix:"
    echo "   1. Verify repository URL"
    echo "   2. Check GitHub authentication"
    echo "   3. Try: git remote remove origin"
    echo "   4. Then run this script again"
    echo ""
fi
