import type { Dictionary } from "@/app/[lang]/dictionaries";

export default function SiteFooter({ dict }: { dict: Dictionary }) {
  return (
    <footer id="site-footer" className="shrink-0 border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
      <div className="max-w-7xl mx-auto px-6 py-3 flex flex-col sm:flex-row items-center justify-between gap-2 text-sm text-gray-400 dark:text-gray-500">
        <span>{dict.footer.copyright.replace("{year}", String(new Date().getFullYear()))}</span>
        <div className="flex gap-6">
          <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.footer.privacy}</a>
          <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.footer.terms}</a>
          <a href="#" className="hover:text-teal-700 dark:hover:text-teal-400 transition-colors">{dict.footer.contact}</a>
        </div>
      </div>
    </footer>
  );
}
