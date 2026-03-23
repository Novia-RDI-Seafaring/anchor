# Anchor UI Documentation

This directory contains the complete user and developer documentation for Anchor UI.

## Structure

- **index.html** - Documentation homepage
- **getting-started.html** - Installation and setup guide
- **user-guide.html** - How to use Anchor UI
- **features.html** - Feature documentation
- **knowledge-base.html** - Knowledge base management
- **chat-interface.html** - Chat interface guide
- **settings.html** - Settings and configuration
- **mcp-tools.html** - Model Context Protocol tools
- **command-line.html** - CLI commands and options
- **architecture.html** - System architecture overview
- **components.html** - Component breakdown
- **api-reference.html** - Backend API documentation
- **contributing.html** - Contribution guide
- **styles.css** - Shared stylesheet
- **nav.js** - Navigation and search functionality

## Viewing the Documentation

Simply open `index.html` in a web browser. The documentation includes:

- **Search functionality** - Search across all pages
- **Navigation sidebar** - Easy navigation between pages
- **Responsive design** - Works on desktop and mobile

## Features

- ✅ Complete user-facing feature documentation
- ✅ Command line options and usage
- ✅ Authentication and configuration options
- ✅ Built-in tools documentation
- ✅ MCP (Model Context Protocol) explanation
- ✅ Architectural overview
- ✅ Component summaries
- ✅ Contribution guide
- ✅ Search functionality
- ✅ Organized, multi-page structure

## Concept Principles

For this repo, the concept should stay easy to explain. The codebase should make it straightforward to answer:

- what the agent does
- how retrieval works
- how evidence becomes canvas output
- how a fact/spec is grounded to source

The repo should privilege clarity over cleverness.

Every new piece of logic should answer:

- does this make the concept easier to explain?
- does this generalize beyond one document?
- can we remove it later without collapsing the core idea?

If the answer is no, the logic should be treated as suspect and kept out of the main concept path.

## Updating Documentation

When updating documentation:

1. Edit the relevant HTML file
2. Maintain consistent styling using `styles.css`
3. Update navigation in `nav.js` if adding new pages
4. Test search functionality
5. Verify links work correctly

## Deployment

The documentation can be deployed as static files to any web server or hosting service like:

- GitHub Pages
- Netlify
- Vercel
- AWS S3
- Any static file hosting

No build process required - just upload the files!


