export function AccountDetails() {
    return (
        <div className="flex flex-col gap-0.5">
            <span className="text-sm font-medium text-black">
                account name
            </span>
            <span className="text-xs text-muted-foreground">
                account settings
            </span>
        </div>
    );
}

export default AccountDetails;