import type { Page } from "@playwright/test";

/**
 * Tìm phần tử bị chính `overflow: hidden` của nó cắt mất nội dung.
 *
 * Lỗi thật ở v2.1.2: `globals.css` là một file phẳng hơn 2.300 dòng với hơn 700 class và
 * không có scope, nên `.download-progress` của trang cập nhật trúng luật `.target-track`
 * của dashboard và bị ép `height: 8px; overflow: hidden`. Hộp cao 24px chứa 63px nội
 * dung: nhãn và thanh tải bị cắt, còn dòng đếm byte bị tô thành một thanh màu. Phần tử
 * vẫn nằm trong DOM nên mọi test đếm phần tử đều xanh — lỗi lọt tới bản phát hành.
 */
export async function findClippedElements(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const clipped = [...document.querySelectorAll<HTMLElement>("body *")]
      .filter((element) => {
        const style = getComputedStyle(element);
        if (style.overflowY !== "hidden" && style.overflowX !== "hidden") return false;
        if (style.display === "none" || element.getClientRects().length === 0) return false;
        // `.sr-only` cố ý là hộp 1px bị cắt để chỉ trình đọc màn hình thấy.
        if (element.clientHeight <= 1 || element.classList.contains("sr-only")) return false;
        const verticalClip = element.scrollHeight - element.clientHeight;
        const horizontalClip = element.scrollWidth - element.clientWidth;
        // Cắt ngang kèm ellipsis là rút gọn có chủ đích, không phải lỗi.
        const ellipsis = style.textOverflow === "ellipsis";
        return verticalClip > 2 || (horizontalClip > 2 && !ellipsis);
      })
      .map((element) => {
        const name = element.className.toString().trim().split(/\s+/).filter(Boolean).join(".");
        return `${element.tagName.toLowerCase()}${name ? `.${name}` : ""} (+${element.scrollHeight - element.clientHeight}px)`;
      });
    return [...new Set(clipped)];
  });
}
