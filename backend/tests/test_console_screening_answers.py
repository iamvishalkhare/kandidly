from types import SimpleNamespace

from app.api.console import _screening_answers


def test_screening_answers_follow_template_order_and_format_values():
    template = SimpleNamespace(
        schema={
            "required": ["full_name", "why_this_role"],
            "x-kandidly": {
                "field_order": ["full_name", "skills", "resume", "why_this_role"],
            },
            "properties": {
                "full_name": {
                    "title": "Full name",
                    "x-builder-type": "text",
                },
                "skills": {
                    "title": "Relevant skills",
                    "x-builder-type": "multi_select",
                },
                "resume": {
                    "title": "Resume",
                    "x-builder-type": "file",
                },
                "why_this_role": {
                    "title": "Why this role",
                    "x-builder-type": "textarea",
                },
            },
        }
    )
    submission = SimpleNamespace(
        answers={
            "full_name": "Ada Lovelace",
            "skills": ["Python", "PostgreSQL"],
            "why_this_role": "",
        }
    )
    file = SimpleNamespace(
        key="application-id/file-id.pdf",
        mime="application/pdf",
    )

    rows = _screening_answers(
        submission,
        template,
        file=file,
        file_url="https://storage.example/resume.pdf",
    )

    assert [row.key for row in rows] == ["full_name", "skills", "resume", "why_this_role"]
    assert rows[0].answer == "Ada Lovelace"
    assert rows[1].answer == "Python, PostgreSQL"
    assert rows[2].answer == "File uploaded"
    assert rows[2].answered is True
    assert rows[2].file_url == "https://storage.example/resume.pdf"
    assert rows[2].file_mime == "application/pdf"
    assert rows[2].file_name == "Resume.pdf"
    assert rows[3].required is True
    assert rows[3].answered is False
    assert rows[3].answer is None
