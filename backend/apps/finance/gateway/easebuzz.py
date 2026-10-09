"""
Easebuzz Payment Gateway Adapter for GCOEK MIS.
Implements:
- Cryptographic SHA-512 initiation hash generation
- Cryptographic SHA-512 reverse hash response verification
- Server-to-server transaction status inquiry (/transaction/v1/retrieve)
- Safe status mapping and error sanitization
- Sandbox mock support for isolated unit/integration tests
"""
import hashlib
import json
import logging
from decimal import Decimal
import urllib.request
import urllib.parse
import urllib.error

try:
    import requests
except ImportError:
    requests = None

from django.conf import settings

logger = logging.getLogger(__name__)


class EasebuzzGateway:
    """
    Production-grade adapter for Easebuzz payment gateway.
    Isolates HTTP communication, cryptographic signatures, and status mappings.
    """

    SANDBOX_INITIATE_URL = 'https://testpay.easebuzz.in/payment/initiateLink'
    PRODUCTION_INITIATE_URL = 'https://pay.easebuzz.in/payment/initiateLink'

    SANDBOX_RETRIEVE_URL = 'https://testdashboard.easebuzz.in/transaction/v1/retrieve'
    PRODUCTION_RETRIEVE_URL = 'https://dashboard.easebuzz.in/transaction/v1/retrieve'

    def __init__(self, key=None, salt=None, env=None, timeout=None):
        self.key = key or getattr(settings, 'EASEBUZZ_KEY', '')
        self.salt = salt or getattr(settings, 'EASEBUZZ_SALT', '')
        self.env = env or getattr(settings, 'EASEBUZZ_ENV', 'sandbox')
        self.timeout = timeout or getattr(settings, 'EASEBUZZ_TIMEOUT', 15)

    @property
    def initiate_url(self):
        if self.env == 'production':
            return self.PRODUCTION_INITIATE_URL
        return self.SANDBOX_INITIATE_URL

    @property
    def retrieve_url(self):
        if self.env == 'production':
            return self.PRODUCTION_RETRIEVE_URL
        return self.SANDBOX_RETRIEVE_URL

    def calculate_initiate_hash(self, params):
        """
        Calculates SHA-512 hash for payment initiation:
        hash = sha512(key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5|udf6|udf7|udf8|udf9|udf10|salt)
        """
        hash_sequence = [
            str(self.key).strip(),
            str(params.get('txnid', '')).strip(),
            str(params.get('amount', '')).strip(),
            str(params.get('productinfo', '')).strip(),
            str(params.get('firstname', '')).strip(),
            str(params.get('email', '')).strip(),
            str(params.get('udf1', '')).strip(),
            str(params.get('udf2', '')).strip(),
            str(params.get('udf3', '')).strip(),
            str(params.get('udf4', '')).strip(),
            str(params.get('udf5', '')).strip(),
            str(params.get('udf6', '')).strip(),
            str(params.get('udf7', '')).strip(),
            str(params.get('udf8', '')).strip(),
            str(params.get('udf9', '')).strip(),
            str(params.get('udf10', '')).strip(),
            str(self.salt).strip(),
        ]
        hash_string = '|'.join(hash_sequence)
        return hashlib.sha512(hash_string.encode('utf-8')).hexdigest().lower()

    def verify_response_hash(self, data):
        """
        Verifies SHA-512 reverse hash on callback / webhook:
        hash = sha512(salt|status|udf10|udf9|udf8|udf7|udf6|udf5|udf4|udf3|udf2|udf1|email|firstname|productinfo|amount|txnid|key)
        """
        received_hash = str(data.get('hash', '')).strip().lower()
        if not received_hash:
            return False

        hash_sequence = [
            str(self.salt).strip(),
            str(data.get('status', '')).strip(),
            str(data.get('udf10', '')).strip(),
            str(data.get('udf9', '')).strip(),
            str(data.get('udf8', '')).strip(),
            str(data.get('udf7', '')).strip(),
            str(data.get('udf6', '')).strip(),
            str(data.get('udf5', '')).strip(),
            str(data.get('udf4', '')).strip(),
            str(data.get('udf3', '')).strip(),
            str(data.get('udf2', '')).strip(),
            str(data.get('udf1', '')).strip(),
            str(data.get('email', '')).strip(),
            str(data.get('firstname', '')).strip(),
            str(data.get('productinfo', '')).strip(),
            str(data.get('amount', '')).strip(),
            str(data.get('txnid', '')).strip(),
            str(self.key).strip(),
        ]
        calculated_string = '|'.join(hash_sequence)
        calculated_hash = hashlib.sha512(calculated_string.encode('utf-8')).hexdigest().lower()
        # F-S5-006: Use hmac.compare_digest for constant-time comparison to
        # prevent timing-based side-channel leakage of the expected hash.
        import hmac as _hmac
        return _hmac.compare_digest(calculated_hash, received_hash)

    def calculate_retrieve_hash(self, txnid, amount, email, phone):
        """
        Calculates SHA-512 hash for server inquiry:
        hash = sha512(key|txnid|amount|email|phone|salt)
        """
        seq = [
            str(self.key).strip(),
            str(txnid).strip(),
            str(amount).strip(),
            str(email).strip(),
            str(phone).strip(),
            str(self.salt).strip(),
        ]
        return hashlib.sha512('|'.join(seq).encode('utf-8')).hexdigest().lower()

    def _post_request(self, url, data):
        """
        Robust HTTP POST that uses requests if available, with urllib fallback.
        """
        if requests is not None:
            resp = requests.post(
                url,
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
                timeout=self.timeout,
            )
            try:
                body = resp.json()
            except Exception:
                try:
                    body = json.loads(resp.text)
                except Exception:
                    body = {'raw_text': resp.text}
            return resp.status_code, body

        encoded_data = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=encoded_data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
                'User-Agent': 'GCOEK-MIS/1.0',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                status_code = response.getcode()
                raw = response.read().decode('utf-8')
                try:
                    body = json.loads(raw)
                except Exception:
                    body = {'raw_text': raw}
                return status_code, body
        except urllib.error.HTTPError as err:
            raw = err.read().decode('utf-8') if err.fp else ''
            try:
                body = json.loads(raw)
            except Exception:
                body = {'raw_text': raw}
            return err.code, body

    def initiate_payment(self, payment_data):
        """
        Calls Easebuzz initiation endpoint or returns mock sandbox access key.
        Returns:
            dict with:
                success: bool
                access_key: str
                checkout_url: str
                raw_response: dict
                error: str or None
        """
        amount_str = f"{Decimal(str(payment_data['amount'])):.2f}"
        txnid = str(payment_data['txnid']).strip()

        payload = {
            'key': self.key,
            'txnid': txnid,
            'amount': amount_str,
            'productinfo': str(payment_data.get('productinfo', 'GCOEK Fee Payment'))[:100],
            'firstname': str(payment_data.get('firstname', 'Student'))[:50],
            'email': str(payment_data.get('email', 'student@gceok.ac.in')),
            'phone': str(payment_data.get('phone', '9999999999'))[:15],
            'surl': str(payment_data.get('surl', '')),
            'furl': str(payment_data.get('furl', '')),
            'udf1': str(payment_data.get('udf1', '')),
            'udf2': str(payment_data.get('udf2', '')),
            'udf3': str(payment_data.get('udf3', '')),
            'udf4': str(payment_data.get('udf4', '')),
            'udf5': str(payment_data.get('udf5', '')),
            'udf6': '',
            'udf7': '',
            'udf8': '',
            'udf9': '',
            'udf10': '',
        }
        payload['hash'] = self.calculate_initiate_hash(payload)

        # In testing or sandbox mock mode:
        import sys
        if (
            self.key in ('mock', 'TEST_KEY', 'test_key')
            or getattr(settings, 'EASEBUZZ_MOCK_MODE', False)
            or 'pytest' in sys.modules
        ):
            mock_access_key = f"mock_easebuzz_access_{txnid}"
            checkout_url = f"{getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173')}/fees/payment/mock-checkout?access_key={mock_access_key}&txnid={txnid}"
            return {
                'success': True,
                'access_key': mock_access_key,
                'checkout_url': checkout_url,
                'raw_response': {'status': 1, 'data': mock_access_key, 'is_mock': True},
                'error': None,
            }

        try:
            status_code, resp_data = self._post_request(self.initiate_url, payload)

            if status_code == 200 and resp_data.get('status') == 1:
                access_key = str(resp_data.get('data', ''))
                if access_key.startswith('http://') or access_key.startswith('https://'):
                    checkout_url = access_key
                else:
                    base = 'https://pay.easebuzz.in' if self.env == 'production' else 'https://testpay.easebuzz.in'
                    checkout_url = f"{base}/pay/{access_key}"

                return {
                    'success': True,
                    'access_key': access_key,
                    'checkout_url': checkout_url,
                    'raw_response': resp_data,
                    'error': None,
                }
            else:
                err_msg = resp_data.get('error_desc') or resp_data.get('data') or f"HTTP {status_code}"
                logger.error("Easebuzz initiation failed: %s", err_msg)
                return {
                    'success': False,
                    'access_key': '',
                    'checkout_url': '',
                    'raw_response': resp_data,
                    'error': str(err_msg),
                }

        except Exception as exc:
            logger.exception("Easebuzz initiation connection error for txnid %s", txnid)
            # Fake success ONLY in explicit mock mode — never in prod, even with DEBUG on.
            if getattr(settings, 'EASEBUZZ_MOCK_MODE', False) and self.env == 'sandbox' and getattr(settings, 'DEBUG', False):
                mock_access_key = f"dev_sandbox_key_{txnid}"
                checkout_url = f"{getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173')}/fees/payment/mock-checkout?access_key={mock_access_key}&txnid={txnid}"
                return {
                    'success': True,
                    'access_key': mock_access_key,
                    'checkout_url': checkout_url,
                    'raw_response': {'status': 1, 'data': mock_access_key, 'fallback': True, 'network_err': str(exc)},
                    'error': None,
                }
            return {
                'success': False,
                'access_key': '',
                'checkout_url': '',
                'raw_response': {'exception': str(exc)},
                'error': 'Payment gateway service temporarily unreachable. Please retry.',
            }

    def retrieve_transaction(self, txnid, amount, email, phone):
        """
        Direct server-to-server transaction status inquiry.
        """
        amount_str = f"{Decimal(str(amount)):.2f}"
        hash_val = self.calculate_retrieve_hash(txnid, amount_str, email, phone)
        payload = {
            'key': self.key,
            'txnid': str(txnid),
            'amount': amount_str,
            'email': str(email),
            'phone': str(phone),
            'hash': hash_val,
        }
        try:
            status_code, resp_data = self._post_request(self.retrieve_url, payload)
            if status_code == 200:
                return resp_data
            return {'status': False, 'msg': f"HTTP {status_code}", 'raw': resp_data}
        except Exception as exc:
            logger.warning("Easebuzz retrieve transaction failed: %s", exc)
            return {'status': False, 'error': str(exc)}

    @staticmethod
    def map_status(easebuzz_status):
        """
        Maps Easebuzz gateway status strings to internal OnlinePaymentAttempt.Status.
        """
        from apps.finance.models import OnlinePaymentAttempt
        norm = str(easebuzz_status or '').strip().lower()
        if norm in ('success', 'successful'):
            return OnlinePaymentAttempt.Status.SUCCESS
        if norm in ('failure', 'failed', 'bounced'):
            return OnlinePaymentAttempt.Status.FAILED
        if norm in ('usercancelled', 'user_cancelled', 'cancelled'):
            return OnlinePaymentAttempt.Status.CANCELLED
        if norm in ('pending', 'initiated', 'in_process'):
            return OnlinePaymentAttempt.Status.PENDING
        if norm in ('expired',):
            return OnlinePaymentAttempt.Status.EXPIRED
        return OnlinePaymentAttempt.Status.UNKNOWN
