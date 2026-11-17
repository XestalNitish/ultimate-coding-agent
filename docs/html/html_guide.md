# HTML5 and Modern Web UI Reference

## Semantic HTML5 Structure
Use modern semantic tags for accessibility, clean DOM structure, and search engine optimization.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Agent Interface</title>
</head>
<body>
    <header class="app-header">
        <h1>Civic Tech Portal</h1>
        <nav>
            <a href="#schemes">Eligible Schemes</a>
            <a href="#profile">Profile</a>
        </nav>
    </header>
    <main class="container">
        <section id="schemes" class="card-grid">
            <!-- Dynamic Scheme Cards -->
        </section>
    </main>
</body>
</html>
```

## Responsive Forms & Inputs
Form design for citizen input, document uploads, and validation.

```html
<form id="scheme-form" method="POST" action="/submit">
    <div class="form-group">
        <label for="full-name">Full Name (As per Aadhaar):</label>
        <input type="text" id="full-name" name="full_name" required minlength="3">
    </div>
    <div class="form-group">
        <label for="income">Annual Family Income (INR):</label>
        <input type="number" id="income" name="annual_income" required min="0">
    </div>
    <div class="form-group">
        <label for="category">Category:</label>
        <select id="category" name="category" required>
            <option value="General">General</option>
            <option value="OBC">OBC</option>
            <option value="SC">SC</option>
            <option value="ST">ST</option>
        </select>
    </div>
    <button type="submit" class="btn-primary">Verify Eligibility</button>
</form>
```

## Modern CSS Embedded Styling
Clean glassmorphic and responsive UI cards.

```html
<style>
    :root {
        --primary: #2563eb;
        --bg-dark: #0f172a;
        --card-bg: rgba(30, 41, 59, 0.7);
    }
    body {
        font-family: system-ui, -apple-system, sans-serif;
        background: var(--bg-dark);
        color: #f8fafc;
        margin: 0;
        padding: 24px;
    }
    .card {
        background: var(--card-bg);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 20px;
        backdrop-filter: blur(8px);
    }
</style>
```
