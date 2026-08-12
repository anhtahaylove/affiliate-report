import type { AccountDirectory } from "@/lib/account-directory";

export function AccountIdentity({ directory, code, className = "" }: { directory: AccountDirectory; code: string | null | undefined; className?: string }) {
  const identity = directory.get(code);
  return (
    <span className={`account-identity${className ? ` ${className}` : ""}`} aria-label={identity.accessibleName} title={identity.accessibleName}>
      <span className="account-identity-name">{identity.primary}</span>
      {identity.secondary ? <span className="account-identity-code" aria-hidden="true">{identity.secondary}</span> : null}
    </span>
  );
}
