<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# End-to-end Testig Rules

You may need to run end-to-end testing on each change. Don't use default ports 8000 for backend and 3000 for the frontend, use ports 8001 and 3001 respectively. If you need a database to run a test backend version, set up a MongoDB instance for that, don't use the one that is running on the dev machine.
Always kill instances after tests end.
