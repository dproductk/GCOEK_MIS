import markdown_it

md = markdown_it.MarkdownIt().disable('linkify').enable('table')
with open(r'c:\Users\SARTHAK\Desktop\GCEOK_MIS\docs\USER_MANUAL.md', 'r', encoding='utf-8') as f:
    text = f.read()

html_body = md.render(text)

full_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GCOEK MIS — Comprehensive User Manual & Operations Guide</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary: #0284c7;
            --primary-dark: #0369a1;
            --primary-light: #e0f2fe;
            --text-main: #0f172a;
            --text-muted: #475569;
            --bg-page: #f8fafc;
            --bg-card: #ffffff;
            --border: #e2e8f0;
            --accent: #2563eb;
            --success: #16a34a;
            --warning: #d97706;
            --danger: #dc2626;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-page);
            color: var(--text-main);
            line-height: 1.7;
            padding: 40px 20px;
        }}
        .manual-container {{
            max-width: 1040px;
            margin: 0 auto;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 56px 64px;
            box-shadow: 0 4px 20px -2px rgba(0,0,0,0.05);
        }}
        h1 {{
            font-size: 2.2rem;
            font-weight: 800;
            color: #0f172a;
            margin-bottom: 8px;
            letter-spacing: -0.02em;
        }}
        h2 {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #1e293b;
            margin-top: 40px;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 2px solid #f1f5f9;
        }}
        h3 {{
            font-size: 1.2rem;
            font-weight: 600;
            color: #334155;
            margin-top: 28px;
            margin-bottom: 12px;
        }}
        h4 {{
            font-size: 1.05rem;
            font-weight: 600;
            color: #475569;
            margin-top: 20px;
            margin-bottom: 8px;
        }}
        p {{
            margin-bottom: 16px;
            color: var(--text-muted);
        }}
        strong {{
            color: #0f172a;
        }}
        hr {{
            border: 0;
            height: 1px;
            background: #e2e8f0;
            margin: 36px 0;
        }}
        ul, ol {{
            margin-left: 24px;
            margin-bottom: 18px;
            color: var(--text-muted);
        }}
        li {{
            margin-bottom: 6px;
        }}
        table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            margin: 24px 0;
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
            font-size: 0.95rem;
        }}
        th, td {{
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background: #f8fafc;
            font-weight: 600;
            color: #1e293b;
            border-bottom: 2px solid var(--border);
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        tr:hover td {{
            background: #fdfdfe;
        }}
        img {{
            max-width: 100%;
            height: auto;
            border-radius: 12px;
            border: 1px solid #cbd5e1;
            margin: 24px 0 8px 0;
            box-shadow: 0 10px 15px -3px rgba(0,0,0,0.07), 0 4px 6px -4px rgba(0,0,0,0.05);
            display: block;
        }}
        em {{
            display: block;
            font-size: 0.88rem;
            color: #64748b;
            text-align: center;
            margin-bottom: 24px;
            font-style: italic;
        }}
        blockquote {{
            background: #f8fafc;
            border-left: 4px solid var(--primary);
            padding: 16px 20px;
            border-radius: 0 8px 8px 0;
            margin: 24px 0;
            color: #334155;
        }}
        blockquote p {{
            margin-bottom: 0;
            color: inherit;
        }}
        code {{
            font-family: 'JetBrains Mono', monospace;
            background: #f1f5f9;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.9em;
            color: #0f172a;
        }}
        pre {{
            background: #0f172a;
            color: #f8fafc;
            padding: 18px 20px;
            border-radius: 10px;
            overflow-x: auto;
            margin: 20px 0;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.9rem;
        }}
        pre code {{
            background: transparent;
            color: inherit;
            padding: 0;
        }}
        a {{
            color: var(--accent);
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        @media print {{
            body {{
                background: #fff;
                padding: 0;
            }}
            .manual-container {{
                border: none;
                box-shadow: none;
                padding: 0;
                max-width: 100%;
            }}
            img {{
                page-break-inside: avoid;
                max-height: 480px;
            }}
            h2, h3 {{
                page-break-after: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="manual-container">
        {html_body}
    </div>
</body>
</html>'''

with open(r'c:\Users\SARTHAK\Desktop\GCEOK_MIS\docs\USER_MANUAL.html', 'w', encoding='utf-8') as f:
    f.write(full_html)

print('USER_MANUAL.html successfully written!')
