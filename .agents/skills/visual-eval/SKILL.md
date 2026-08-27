---
name: visual-eval
description: Run a visual comparison between main (base) and current branch (eval) for a test scenario. Annotate frontend differences with bounding boxes.
---

# Visual Evaluation Workflow

When the user invokes this skill and provides a test scenario, you must orchestrate a complete visual regression test comparing the `main` branch (base) with the current working branch (eval). You will write and execute the necessary scripts using your tools to accomplish this.

Follow these exact steps in order:

## 1. Setup Base Environment (`main`)
* Use `git worktree add /tmp/visual-eval-base main` to create an isolated workspace for the base branch.
* Navigate to `/tmp/visual-eval-base` and install dependencies.
* Start the base backend and frontend on dedicated ports, use Backend on 8001, Frontend on 3001. Ensure the frontend is configured to point to the base backend.
* Wait for both services to become healthy.

## 2. Setup Eval Environment (Current Branch)
* In the current working directory, install dependencies.
* Start the eval backend and frontend on different dedicated ports, use Backend on 8002, Frontend on 3002.
* Wait for these services to become healthy.

## 3. Execute Scenario & Capture Screens
* Write a temporary script using a browser automation tool (such as Playwright via `npx playwright`) to perform the user's test scenario.
* The script must execute the exact same steps on both the base frontend (`http://localhost:3001`) and the eval frontend (`http://localhost:3002`).
* After every logical step in the scenario, capture a full-page screenshot for both environments (e.g., `step1_base.png`, `step1_eval.png`).
* Execute the browser script.

## 4. Compare and Annotate Differences
* Write a Python script to calculate the visual differences and draw bounding boxes. (Create a temporary virtual environment and install `opencv-python` and `numpy` if needed).
  - Use only Python libraries for image processing (e.g., OpenCV, NumPy). Do not use any external visual diff tools and 
    don't use LLM for that.
* For each pair of screenshots:
  1. Load both images and convert them to grayscale.
  2. Crop images to the view e.g. modal form, widget, etc.
  3. Execute the comparison script.
  4. Compute the absolute difference between them (`cv2.absdiff`).
  5. Apply a binary threshold to isolate the changed pixels.
  6. Find the contours of the thresholded differences.
  7. Draw visible bounding boxes (e.g., in bright red, thickness 2) around the contours on a copy of both **base** and **eval** screenshots.
  8. Combine annotaged base and eval screenshots into a side-by-side image. Map each annotation between two images. Connect each annotation on base side with a corresponding one on eval side with a line. If there are unmatched annotations, indicate them with a label (e.g., "New" or "Removed").
  9. Save this final annotated image as `step{N}_annotated.png`.
  10. Copy annotated image into the current project into the evals/date-time-dir-name/.

## 5. Teardown
* Terminate the background processes you started for both environments (the Node/Python servers).
* Run `git worktree remove -f /tmp/visual-eval-base` to clean up the temporary base workspace.

## 6. Report Results
* Output the file paths of the generated `stepX_annotated.png` images.
* Provide a brief summary of the visual differences found. If no differences were found, explicitly state that the screens are visually identical.