import { useEffect, useState } from 'react';
import { api } from '../services/api';

interface Props {
  onContinue: () => void;
}

export function PaymentReturnPage({ onContinue }: Props) {
  const [message, setMessage] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('status') !== 'successful') {
      return 'The payment was not completed. No plan has been activated.';
    }
    if (!params.get('transaction_id') || !params.get('tx_ref')) {
      return 'Payment details were missing, so we could not verify the transaction.';
    }
    return 'Confirming your payment with Flutterwave…';
  });
  const [verified, setVerified] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const transactionId = params.get('transaction_id') || '';
    const txRef = params.get('tx_ref') || '';
    const paymentStatus = params.get('status');

    if (paymentStatus !== 'successful' || !transactionId || !txRef) return;

    let active = true;
    api.verifyPayment(transactionId, txRef).then(() => {
      if (!active) return;
      setVerified(true);
      setMessage('Payment confirmed. You now have unlimited quotations for one month.');
    }).catch((error: unknown) => {
      if (!active) return;
      setMessage(error instanceof Error
        ? error.message
        : 'We could not verify this payment. Please contact support before paying again.');
    });

    return () => { active = false; };
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[var(--bg)]">
      <div className="card w-full max-w-sm text-center">
        <div className="flex items-center justify-center gap-2 mb-4">
          <span className="font-semibold text-lg">quoteGEN</span>
          <span className="chip chip-gold">AI</span>
        </div>
        <h1 className="text-lg font-semibold mb-2">
          {verified ? 'You’re all set!' : 'Payment update'}
        </h1>
        <p className="text-sm text-[var(--text-muted)] mb-5" role="status">{message}</p>
        {message.startsWith('Confirming') ? null : (
          <button type="button" className="btn btn-primary w-full" onClick={onContinue}>
            Return to quoteGEN
          </button>
        )}
      </div>
    </div>
  );
}
