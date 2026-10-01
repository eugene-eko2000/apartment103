"use client";

import dynamic from "next/dynamic";
import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import getCaretCoordinates from "textarea-caret";
import { imageUrl, type ImageAsset, type MessageTemplateVersion } from "@/lib/api";
import {
  PLACEHOLDERS,
  SAMPLE_VALUES,
  completionRange,
  findPlaceholderTrigger,
  imageToken,
  matchPlaceholders,
  placeholderToken,
  spliceText,
  substitutePlaceholders,
  type Placeholder,
  type PlaceholderTrigger,
} from "@/lib/message-placeholders";
import { useTheme } from "@/lib/theme-context";

// The editor touches `window`/`document` while loading, so it is only ever
// rendered on the client. The `nohighlight` build skips the code-syntax
// highlighter, which guest messages have no use for.
const MDEditor = dynamic(() => import("@uiw/react-md-editor/nohighlight"), {
  ssr: false,
  loading: () => <div className="h-[260px] rounded-lg border border-slate-300 dark:border-slate-600" />,
});
const MarkdownPreview = dynamic(
  () => import("@uiw/react-md-editor/nohighlight").then((m) => m.default.Markdown),
  { ssr: false }
);

type Field = HTMLInputElement | HTMLTextAreaElement;

function isTextField(target: EventTarget | null): target is Field {
  return target instanceof HTMLTextAreaElement || (target instanceof HTMLInputElement && target.type === "text");
}

/**
 * Replace [start, end) of `field` with `text` and put the caret after it.
 * Goes through execCommand so the edit lands on the field's own undo stack
 * and fires the same `input` event typing would — which is what both the
 * subject's and the markdown editor's onChange listen to.
 */
function insertIntoField(field: Field, start: number, end: number, text: string) {
  field.focus();
  field.setSelectionRange(start, end);
  if (!document.execCommand("insertText", false, text)) {
    field.value = spliceText(field.value, start, end, text);
    field.setSelectionRange(start + text.length, start + text.length);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  }
}

interface Autocomplete {
  field: Field;
  trigger: PlaceholderTrigger;
  options: Placeholder[];
  active: number;
  x: number;
  y: number;
}

export default function MessageVersionEditor({
  version,
  onChange,
  images,
  uploading,
  uploadError,
  onUploadImages,
  onRemoveImage,
}: {
  version: MessageTemplateVersion;
  onChange: (version: MessageTemplateVersion) => void;
  /** The message's attached images — shared by every language version. */
  images: ImageAsset[];
  uploading: boolean;
  uploadError: string | null;
  onUploadImages: (files: File[]) => void;
  onRemoveImage: (image: ImageAsset) => void;
}) {
  const { resolvedTheme } = useTheme();
  const [mode, setMode] = useState<"write" | "preview">("write");
  const [autocomplete, setAutocomplete] = useState<Autocomplete | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Where a clicked placeholder chip goes: the subject or the body,
  // whichever was focused last. Clicking a chip doesn't steal focus (see
  // its onMouseDown), so the field keeps its caret too.
  const lastFieldRef = useRef<Field | null>(null);

  const refreshAutocomplete = (field: Field) => {
    const caret = field.selectionStart ?? 0;
    const trigger = field.selectionEnd === caret ? findPlaceholderTrigger(field.value, caret) : null;
    const options = trigger ? matchPlaceholders(trigger.query) : [];
    if (!trigger || options.length === 0) {
      setAutocomplete(null);
      return;
    }
    const coords = getCaretCoordinates(field, trigger.start);
    const rect = field.getBoundingClientRect();
    setAutocomplete((previous) => ({
      field,
      trigger,
      options,
      active: previous && previous.trigger.query === trigger.query ? previous.active : 0,
      x: rect.left + coords.left - field.scrollLeft,
      y: rect.top + coords.top - field.scrollTop + coords.height + 4,
    }));
  };

  const accept = (placeholder: Placeholder) => {
    if (!autocomplete) return;
    const { field, trigger } = autocomplete;
    const [start, end] = completionRange(field.value, trigger, field.selectionStart ?? 0);
    setAutocomplete(null);
    insertIntoField(field, start, end, placeholderToken(placeholder.name));
  };

  const insertChip = (placeholder: Placeholder) => {
    const field = lastFieldRef.current?.isConnected
      ? lastFieldRef.current
      : wrapperRef.current?.querySelector("textarea");
    if (!field) return;
    setAutocomplete(null);
    insertIntoField(field, field.selectionStart ?? field.value.length, field.selectionEnd ?? field.value.length, placeholderToken(placeholder.name));
  };

  // Images only make sense in the message text (the subject is plain
  // text), so they always go into the body, at its caret — which the
  // textarea keeps while focus is elsewhere.
  const insertImage = (image: ImageAsset) => {
    const body = wrapperRef.current?.querySelector("textarea");
    if (!body) return;
    setAutocomplete(null);
    insertIntoField(body, body.selectionStart ?? body.value.length, body.selectionEnd ?? body.value.length, imageToken(image._id));
  };

  // Capture phase: runs before the markdown editor's own keydown listener on
  // its textarea (Tab indents, Enter continues a list) and before the
  // modal's Escape-to-close, so while the list is open these keys drive it.
  const onKeyDownCapture = (e: React.KeyboardEvent) => {
    if (!autocomplete) return;
    const count = autocomplete.options.length;
    const take = () => {
      e.preventDefault();
      e.stopPropagation();
    };
    if (e.key === "ArrowDown") {
      take();
      setAutocomplete({ ...autocomplete, active: (autocomplete.active + 1) % count });
    } else if (e.key === "ArrowUp") {
      take();
      setAutocomplete({ ...autocomplete, active: (autocomplete.active - 1 + count) % count });
    } else if (e.key === "Enter" || e.key === "Tab") {
      take();
      accept(autocomplete.options[autocomplete.active]);
    } else if (e.key === "Escape") {
      take();
      setAutocomplete(null);
    }
  };

  const onCaretMove = (e: React.SyntheticEvent) => {
    if (isTextField(e.target)) refreshAutocomplete(e.target);
  };

  const onKeyUp = (e: React.KeyboardEvent) => {
    // Already handled on the way down; re-reading the caret here would
    // reopen a list that Escape/Enter just closed.
    if (["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"].includes(e.key)) return;
    onCaretMove(e);
  };

  const preview = mode === "preview";

  return (
    <div
      ref={wrapperRef}
      className="space-y-3"
      onKeyDownCapture={onKeyDownCapture}
      onInput={onCaretMove}
      onKeyUp={onKeyUp}
      onClick={onCaretMove}
      onFocus={(e) => {
        if (isTextField(e.target)) lastFieldRef.current = e.target;
      }}
      onBlur={() => setAutocomplete(null)}
    >
      <section aria-label="Images">
        <div className="flex items-center gap-3 mb-1.5">
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Images <span className="font-normal">— double-click one to insert it into the text</span>
          </p>
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileInputRef.current?.click()}
            className="ml-auto px-2.5 py-1 rounded-md border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-600 disabled:opacity-60 cursor-pointer"
          >
            {uploading ? "Uploading…" : "Upload Image"}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif"
            multiple
            hidden
            aria-label="Upload Image"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              e.target.value = "";
              if (files.length > 0) onUploadImages(files);
            }}
          />
        </div>
        {images.length === 0 ? (
          <p className="text-xs text-slate-400 dark:text-slate-500">No images yet.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {images.map((image) => (
              <li key={image._id} className="relative group">
                <button
                  type="button"
                  title={preview ? "Switch to Edit to insert" : "Double-click to insert"}
                  aria-label={`Insert image ${image.key}`}
                  onMouseDown={(e) => e.preventDefault()}
                  onDoubleClick={() => !preview && insertImage(image)}
                  className="block w-20 h-20 rounded-md overflow-hidden border border-slate-200 dark:border-slate-600 hover:ring-2 hover:ring-indigo-400 cursor-copy"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element -- admin thumbnail of an uploaded file */}
                  <img src={imageUrl(image.key)} alt="" className="w-full h-full object-cover" draggable={false} />
                </button>
                <button
                  type="button"
                  aria-label={`Remove image ${image.key}`}
                  title="Remove from this message"
                  onClick={() => onRemoveImage(image)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-500 text-slate-500 dark:text-slate-300 text-xs leading-none hover:text-red-600 opacity-0 group-hover:opacity-100 focus:opacity-100 cursor-pointer"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        {uploadError && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{uploadError}</p>}
      </section>

      <div>
        <p className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1.5">
          Placeholders <span className="font-normal">— click to insert, or type {"{{"} in the subject or text</span>
        </p>
        <div className="flex flex-wrap gap-1.5" role="toolbar" aria-label="Placeholders">
          {PLACEHOLDERS.map((placeholder) => (
            <button
              key={placeholder.name}
              type="button"
              title={placeholder.label}
              disabled={preview}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => insertChip(placeholder)}
              className="px-2 py-1 rounded-md bg-indigo-50 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300 font-mono text-xs hover:bg-indigo-100 dark:hover:bg-indigo-900/70 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {placeholderToken(placeholder.name)}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-700" role="tablist" aria-label="Editor mode">
        {(["write", "preview"] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            onClick={() => {
              setAutocomplete(null);
              setMode(m);
            }}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 -mb-px cursor-pointer ${
              mode === m
                ? "border-indigo-600 text-indigo-700 dark:text-indigo-400"
                : "border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-100"
            }`}
          >
            {m === "write" ? "Edit" : "Preview"}
          </button>
        ))}
      </div>

      {preview ? (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-4 space-y-3">
          <p className="text-xs text-slate-500 dark:text-slate-400">Shown with sample booking values.</p>
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
            {substitutePlaceholders(version.subject, SAMPLE_VALUES) || <span className="italic font-normal">No subject</span>}
          </p>
          <div data-color-mode={resolvedTheme}>
            <MarkdownPreview
              source={substitutePlaceholders(
                version.body_markdown,
                SAMPLE_VALUES,
                Object.fromEntries(images.map((image) => [image._id, `![](${imageUrl(image.key)})`]))
              )}
              style={{ background: "transparent", fontSize: 14 }}
            />
          </div>
        </div>
      ) : (
        <>
          <div>
            <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">
              Subject
              <input
                type="text"
                required
                value={version.subject}
                onChange={(e) => onChange({ ...version, subject: e.target.value })}
                className="mt-1 w-full px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-100 text-sm font-normal focus:outline-none focus:ring-1 focus:ring-indigo-400 focus:border-indigo-500"
              />
            </label>
          </div>
          <div data-color-mode={resolvedTheme}>
            <p className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Message text (Markdown)</p>
            <MDEditor
              value={version.body_markdown}
              onChange={(body) => onChange({ ...version, body_markdown: body ?? "" })}
              preview="edit"
              extraCommands={[]}
              height={260}
              visibleDragbar={false}
              textareaProps={{ "aria-label": "Message text" }}
            />
          </div>
        </>
      )}

      {autocomplete &&
        createPortal(
          <ul
            role="listbox"
            aria-label="Placeholder suggestions"
            className="fixed z-[110] min-w-56 max-h-64 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 shadow-lg py-1 text-sm"
            style={{ left: autocomplete.x, top: autocomplete.y }}
          >
            {autocomplete.options.map((option, i) => (
              <li
                key={option.name}
                role="option"
                aria-selected={i === autocomplete.active}
                onMouseDown={(e) => {
                  e.preventDefault();
                  accept(option);
                }}
                onMouseEnter={() => setAutocomplete({ ...autocomplete, active: i })}
                className={`px-3 py-1.5 cursor-pointer ${
                  i === autocomplete.active
                    ? "bg-indigo-50 dark:bg-indigo-900/50 text-indigo-800 dark:text-indigo-200"
                    : "text-slate-700 dark:text-slate-200"
                }`}
              >
                <span className="font-mono text-xs">{placeholderToken(option.name)}</span>
                <span className="block text-xs text-slate-500 dark:text-slate-400">{option.label}</span>
              </li>
            ))}
          </ul>,
          document.body
        )}
    </div>
  );
}
