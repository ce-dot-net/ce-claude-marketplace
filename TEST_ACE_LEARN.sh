#!/bin/bash
# TEST ACE LEARNING - Commands to paste in another terminal

echo "==============================================="
echo "🧪 ACE LEARNING TEST COMMANDS"
echo "==============================================="
echo ""

# 1. Check ACE server status
echo "1️⃣  CHECK ACE SERVER STATUS:"
echo "curl -s http://localhost:9000/ | jq"
curl -s http://localhost:9000/ | jq
echo ""

# 2. Check ACE playbook
echo "2️⃣  CHECK CURRENT PLAYBOOK:"
echo "curl -s -H 'Authorization: Bearer ace_D1GGNrRGJFe9sqVe1gIfUmcOTDAvYqqcxqztO0Fuqsc' -H 'X-ACE-Project: prj_e3bfc955c48ce974' http://localhost:9000/playbook | jq '.total_bullets'"
curl -s -H 'Authorization: Bearer ace_D1GGNrRGJFe9sqVe1gIfUmcOTDAvYqqcxqztO0Fuqsc' -H 'X-ACE-Project: prj_e3bfc955c48ce974' http://localhost:9000/playbook | jq '.total_bullets'
echo ""

# 3. Check MCP client version
echo "3️⃣  CHECK MCP CLIENT VERSION:"
echo "npm view @ce-dot-net/ace-client@3.1.5 version"
npm view @ce-dot-net/ace-client@3.1.5 version
echo ""

# 4. Check if ace_learn is in published package
echo "4️⃣  CHECK IF ACE_LEARN IN PUBLISHED PACKAGE:"
echo "cd /tmp && npm pack @ce-dot-net/ace-client@3.1.5 && tar -xzf ce-dot-net-ace-client-3.1.5.tgz && grep -c 'ace_learn' package/dist/index.js && rm -rf package ce-dot-net-ace-client-3.1.5.tgz"
cd /tmp && npm pack @ce-dot-net/ace-client@3.1.5 2>&1 | tail -2 && tar -xzf ce-dot-net-ace-client-3.1.5.tgz && echo "ace_learn occurrences: $(grep -c 'ace_learn' package/dist/index.js)" && rm -rf package ce-dot-net-ace-client-3.1.5.tgz
cd - > /dev/null
echo ""

# 5. Test direct server API
echo "5️⃣  TEST DIRECT SERVER API (should work):"
echo "curl -X POST http://localhost:9000/traces -H 'Content-Type: application/json' -H 'Authorization: Bearer ace_D1GGNrRGJFe9sqVe1gIfUmcOTDAvYqqcxqztO0Fuqsc' -H 'X-ACE-Project: prj_e3bfc955c48ce974' -d '{\"task\":\"test\",\"trajectory\":[],\"result\":{\"success\":true,\"output\":\"test\"},\"playbook_used\":[]}' | jq"
curl -s -X POST http://localhost:9000/traces \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer ace_D1GGNrRGJFe9sqVe1gIfUmcOTDAvYqqcxqztO0Fuqsc' \
  -H 'X-ACE-Project: prj_e3bfc955c48ce974' \
  -d '{"task":"test","trajectory":[],"result":{"success":true,"output":"test"},"playbook_used":[]}' | jq
echo ""

echo "==============================================="
echo "✅ ALL TESTS COMPLETE"
echo "==============================================="
echo ""
echo "📝 FINDINGS:"
echo "- ACE Server: $(curl -s http://localhost:9000/ | jq -r '.status')"
echo "- Published Package Has ace_learn: Check output above"
echo "- Server /traces endpoint: Check if 200 OK above"
echo ""
echo "🔍 NEXT STEPS:"
echo "1. If server tests pass, issue is MCP tool registration in Claude Code"
echo "2. Check MCP server tool list response"
echo "3. May need to rebuild and republish MCP client"
