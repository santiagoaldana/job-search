"""
Application Engine — human-in-the-loop Playwright form filling.
Playwright opens the apply URL, pre-fills from CV JSON,
then pauses for Santiago to review before final submit.
"""

import json
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent.parent


async def launch_application(application, apply_url: str, cv_version_path: Optional[str]) -> dict:
    """
    Open the application form in a visible browser, pre-fill from CV JSON,
    and pause for human review before submit.
    Returns status dict.
    """
    from app.services.cv_manager import load_master_cv, load_version

    # Load the CV version to use
    if cv_version_path:
        version_name = Path(cv_version_path).stem
        cv = load_version(version_name)
    else:
        cv = load_master_cv()

    contact = cv.get("contact", {})
    name = cv.get("name", "Santiago Aldana")
    email = contact.get("email", "aldana.santiago@gmail.com")
    phone = contact.get("phone", "617-216-7003")
    location = contact.get("location", "Cambridge, MA")
    linkedin = contact.get("linkedin", "linkedin.com/in/santiago-aldana")

    # Build plain-text experience for form text fields
    exp_text = _build_experience_text(cv)

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, slow_mo=200)
            page = await browser.new_page()

            await page.goto(apply_url, wait_until="networkidle", timeout=30000)

            # Try to fill common form fields
            await _fill_form_fields(page, {
                "name": name,
                "first_name": name.split()[0],
                "last_name": " ".join(name.split()[1:]),
                "email": email,
                "phone": phone,
                "location": location,
                "linkedin": f"https://{linkedin}" if not linkedin.startswith("http") else linkedin,
                "resume_text": exp_text,
            })

            # Upload PDF if available
            cv_pdf = _find_cv_pdf(cv_version_path)
            if cv_pdf and cv_pdf.exists():
                try:
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(str(cv_pdf))
                except Exception:
                    pass

            print("\n" + "=" * 60)
            print("REVIEW & SUBMIT")
            print("The application form has been pre-filled.")
            print("Please review all fields in the browser window.")
            print("Press ENTER here when ready to close (do NOT submit from terminal).")
            print("Submit the form manually in the browser, then press ENTER.")
            print("=" * 60)
            input()

            await browser.close()

        return {
            "status": "browser_closed",
            "message": "Application form was pre-filled. Check browser for submission status.",
            "apply_url": apply_url,
        }

    except ImportError:
        return {
            "status": "playwright_not_installed",
            "message": "Playwright not installed. Run: playwright install chromium",
            "apply_url": apply_url,
            "pre_filled_data": {
                "name": name,
                "email": email,
                "phone": phone,
                "location": location,
                "linkedin": linkedin,
            },
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "apply_url": apply_url,
        }


async def _fill_form_fields(page, data: dict):
    """Attempt to fill common form field patterns."""
    field_patterns = {
        # Standard name patterns
        "[name*='name'][type='text'], [id*='name'][type='text'], [placeholder*='name' i]": data["name"],
        "[name*='first'][type='text'], [id*='first'][type='text'], [placeholder*='first' i]": data["first_name"],
        "[name*='last'][type='text'], [id*='last'][type='text'], [placeholder*='last' i]": data["last_name"],
        # Email
        "[type='email'], [name*='email'], [id*='email']": data["email"],
        # Phone
        "[type='tel'], [name*='phone'], [id*='phone'], [placeholder*='phone' i]": data["phone"],
        # Location
        "[name*='location'], [id*='location'], [name*='city'], [placeholder*='city' i]": data["location"],
        # LinkedIn
        "[name*='linkedin'], [id*='linkedin'], [placeholder*='linkedin' i]": data["linkedin"],
    }

    for selector, value in field_patterns.items():
        try:
            elements = await page.query_selector_all(selector)
            for el in elements[:1]:  # fill first match only
                await el.fill(value)
        except Exception:
            pass


def _build_experience_text(cv: dict) -> str:
    """Build plain-text experience summary for copy-paste into form fields."""
    lines = []
    for exp in cv.get("experience", []):
        lines.append(f"{exp['title']}, {exp['company']} ({exp.get('dates','')})")
        for b in exp.get("bullets", [])[:3]:  # top 3 bullets
            lines.append(f"• {b}")
        lines.append("")
    return "\n".join(lines)[:3000]


def _find_cv_pdf(cv_version_path: Optional[str]) -> Optional[Path]:
    """Find the PDF for the given CV version, or fall back to most recent."""
    output_dir = BASE_DIR / "cv" / "output"
    if cv_version_path:
        stem = Path(cv_version_path).stem
        # Look for a matching PDF
        matches = list(output_dir.glob(f"{stem}*.pdf"))
        if matches:
            return sorted(matches)[-1]
    # Fall back to most recent PDF
    pdfs = sorted(output_dir.glob("*.pdf"))
    return pdfs[-1] if pdfs else None
