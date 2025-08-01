import { DashboardWidgets } from "@/components/dashboard/DashboardWidgets";


export default function DashboardPage() {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-3xl font-bold text-foreground mb-2">Dashboard</h1>
                <p className="text-muted-foreground">Welcome back! Here's your product intelligence overview.</p>
            </div>
            <DashboardWidgets />
        </div>
    );
}
