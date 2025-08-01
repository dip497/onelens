import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';

export function NotFound() {
  const navigate = useNavigate();

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh]">
      <h1 className="text-6xl font-bold text-muted-foreground mb-4">404</h1>
      <h2 className="text-2xl font-semibold mb-2">Page Not Found</h2>
      <p className="text-muted-foreground mb-8">
        The page you're looking for doesn't exist.
      </p>
      <Button onClick={() => navigate('/')}>
        Go to Dashboard
      </Button>
    </div>
  );
}