import { AppRouter } from '@/router/AppRouter';
import { ToastContainer } from '@/components/ui/ToastContainer';

export function App() {
  return (
    <>
      <AppRouter />
      <ToastContainer />
    </>
  );
}
