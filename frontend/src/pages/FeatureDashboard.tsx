import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function FeatureDashboard() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Features</h1>
        <p className="text-muted-foreground">
          Manage and analyze product features across all epics
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Feature Management</CardTitle>
          <CardDescription>
            View and manage all features with priority scoring
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-12 text-muted-foreground">
            Feature dashboard coming soon...
          </div>
        </CardContent>
      </Card>
    </div>
  );
}