# Job description standardiser with a local LLM

Turns job descriptions written in different styles and languages into one template: title, job family, level, location, work model, required years, responsibilities, requirements and languages. A template like this is useful for HR process redesign, job architecture work and clean reporting on open roles.

I did this kind of work at my employer with a locally run model. The real job descriptions are internal, so this repository shows the approach on four fictional samples (English and German).

## Why a local model

- **GDPR:** the model runs on your own machine through [Ollama](https://ollama.com). No text goes to an outside service.
- **Personal data removed first:** e-mail addresses, phone numbers and contact names are taken out before the text reaches the model (`scrub()`).
- **Fixed output:** the model must return JSON that matches the template. Values outside the allowed lists (job family, level, work model) fail validation.
- **Human review:** every record is marked `human_review: pending`. The model drafts; a person approves.

## Run

```
pip install -r requirements.txt

# test the pipeline without a model (keyword rules)
python standardise.py --dry-run

# with a local model
ollama pull llama3.1:8b
python standardise.py
```

Output: `output/standardised.csv` and `output/standardised.json`.

## Dry-run result on the samples

| File | Job family | Level | Location | Work model | Language | Min. years | Personal data removed |
|---|---|---|---|---|---|---|---|
| jd_01 | HR Analytics | Senior | Munich | Hybrid | English | 4 | 3 |
| jd_02 | Payroll | Professional | Hamburg | Not stated | English | 3 | 1 |
| jd_03 | HR Business Partnering | Senior | Berlin | Not stated | German | 5 | 2 |
| jd_04 | Talent Acquisition | Professional | Germany | Remote | English | 2 | 0 |

The dry run fills only the structured fields. The model adds the responsibilities and requirements in short English phrases, also for the German posting.

## Limits

- An 8B model is good at extraction but still makes mistakes on level and job family. That is why the review step stays.
- The personal-data patterns cover common German and international formats, not every possible one.
