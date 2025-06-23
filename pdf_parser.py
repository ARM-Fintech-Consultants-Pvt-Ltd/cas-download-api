import pdfplumber
import json
import re
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List, Optional
from models import CASData, InvestorInfo, PortfolioSummary, MutualFundScheme, Transaction, AdditionalInfo, Gain
from PyPDF2 import PdfReader

class CASParser:
    def __init__(self, pdf_path: str, password: str):
        self.pdf_path = pdf_path
        self.password = password
        self.text = self._extract_text()
        self.cas_data = CASData()

    def _extract_text(self) -> str:
        try:
            # First verify if PDF can be opened with PyPDF2
            with open(self.pdf_path, 'rb') as file:
                pdf = PdfReader(file)
                if pdf.is_encrypted:
                    try:
                        if not pdf.decrypt(self.password):
                            raise ValueError("Invalid PAN number. For CAMS CAS, use your PAN number as the password.")
                    except Exception:
                        raise ValueError("Invalid PAN number. For CAMS CAS, use your PAN number as the password.")

            # Now extract text with pdfplumber
            try:
                with pdfplumber.open(self.pdf_path, password=self.password) as pdf:
                    text = ""
                    for page in pdf.pages:
                        text += page.extract_text() + "\n"
                    
                    # Verify this is a CAMS CAS
                    if not any(marker in text for marker in [
                        "CAMS - Consolidated Account Statement",
                        "Computer Age Management Services Limited",
                        "CAMS Financial Information Services"
                    ]):
                        raise ValueError("This appears to be not a CAMS CAS file. Please ensure you're uploading a CAMS Consolidated Account Statement.")
                    
                    if not text.strip():
                        raise ValueError("No text could be extracted from the PDF. Please ensure this is a valid CAMS CAS PDF.")
                    return text
            except Exception as e:
                if "password" in str(e).lower():
                    raise ValueError("Invalid PAN number. For CAMS CAS, use your PAN number as the password.")
                raise ValueError(f"Error extracting text from PDF: {str(e)}")
        except Exception as e:
            if isinstance(e, ValueError):
                raise e
            raise ValueError(f"Error processing PDF: {str(e)}")

    def parse(self) -> CASData:
        """Parse the CAS PDF and return structured data"""
        # Extract all components
        self._extract_investor_info()
        self._extract_mutual_funds()
        self._calculate_portfolio_summary()
        return self.cas_data

    def to_excel(self, output_path: str) -> None:
        """Export the parsed data to Excel format"""
        data_dict = self.cas_data.to_dict()
        
        # Create Excel writer
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Write each sheet
            pd.DataFrame(data_dict['investor_info']).to_excel(writer, sheet_name='Investor Info', index=False)
            pd.DataFrame(data_dict['portfolio_summary']).to_excel(writer, sheet_name='Portfolio Summary', index=False)
            pd.DataFrame(data_dict['schemes']).to_excel(writer, sheet_name='MF Schemes', index=False)
            pd.DataFrame(data_dict['transactions']).to_excel(writer, sheet_name='MF Transactions', index=False)

    def _extract_investor_info(self) -> None:
        """Extract investor information from the CAS PDF"""
        # Extract PAN
        pan_pattern = r"PAN:\s*([A-Z]{5}\d{4}[A-Z])"
        if pan_match := re.search(pan_pattern, self.text):
            print(f"Found PAN: {pan_match.group(1)}")

        # Extract name - look for lines with PAN
        name_pattern = r"^([^\n]+)\s+PAN:"
        if name_match := re.search(name_pattern, self.text, re.MULTILINE):
            self.cas_data.investor_info.name = name_match.group(1).strip()
            print(f"Found name: {self.cas_data.investor_info.name}")

        # Extract email and mobile
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        if email_match := re.search(email_pattern, self.text):
            self.cas_data.investor_info.email = email_match.group(0)
            print(f"Found email: {self.cas_data.investor_info.email}")

        mobile_pattern = r"Mobile:\s*(\+?\d[\d\s-]{8,}\d)"
        if mobile_match := re.search(mobile_pattern, self.text):
            self.cas_data.investor_info.mobile = mobile_match.group(1).strip()
            print(f"Found mobile: {self.cas_data.investor_info.mobile}")

        # For CAMS, CAS ID is in the filename
        cas_id_pattern = r"CP(\d+)_"
        if cas_id_match := re.search(cas_id_pattern, self.pdf_path):
            self.cas_data.investor_info.cas_id = cas_id_match.group(1)
            print(f"Found CAS ID: {self.cas_data.investor_info.cas_id}")

        # Extract address - look for lines between name and first folio
        if self.cas_data.investor_info.name:
            lines = self.text.split('\n')
            for i, line in enumerate(lines):
                if line.strip() == self.cas_data.investor_info.name:
                    address_lines = []
                    j = i + 1
                    while j < len(lines) and not lines[j].strip().startswith('Folio No:'):
                        line = lines[j].strip()
                        if line and not line.startswith('***') and not line.startswith('Opening Unit'):
                            address_lines.append(line)
                        j += 1
                    if address_lines:
                        address = ' '.join(address_lines)
                        # Clean up address
                        address = re.sub(r'\s*-\s*ISIN:.*$', '', address)
                        address = re.sub(r'\s*-\s*Growth.*$', '', address)
                        address = re.sub(r'\s+', ' ', address)
                        self.cas_data.investor_info.address = address.strip(' ,-')
                        print(f"Found address: {self.cas_data.investor_info.address}")
                        break

    def _extract_mutual_funds(self) -> None:
        """Extract mutual fund information from text"""
        lines = self.text.split('\n')
        
        current_folio = None
        current_amc = None
        current_scheme = None
        current_advisor = None
        current_rta = None
        current_rta_code = None
        
        for i, line in enumerate(lines):
            # Look for folio number lines
            if folio_match := re.search(r'Folio No:\s*([\w\s/-]+)', line):
                current_folio = folio_match.group(1).strip()
                # Try to extract AMC from the next few lines
                for j in range(i+1, min(i+5, len(lines))):
                    if 'Mutual Fund' in lines[j]:
                        current_amc = lines[j].strip()
                        break
                print(f"\nFound folio: {current_folio} ({current_amc})")
                continue
            
            # Look for advisor info
            if advisor_match := re.search(r'ARN-([\d]+)', line):
                current_advisor = f"ARN-{advisor_match.group(1)}"
                print(f"Found advisor: {current_advisor}")
            
            # Look for RTA info
            if 'CAMS' in line:
                current_rta = 'CAMS'
            elif 'KFINTECH' in line:
                current_rta = 'KFINTECH'
            
            # Look for ISIN lines to identify schemes
            if isin_match := re.search(r'ISIN:\s*(INF\w+)', line):
                isin = isin_match.group(1)
                # Get scheme name from previous line
                scheme_name = lines[i-1].strip() if i > 0 else ""
                
                # Create a new scheme
                scheme = MutualFundScheme(
                    folio_number=current_folio,
                    amc=current_amc,
                    name=scheme_name,
                    isin=isin
                )
                
                # Set additional info
                scheme.additional_info.advisor = current_advisor
                scheme.additional_info.rta = current_rta
                scheme.additional_info.rta_code = current_rta_code
                
                print(f"Found scheme: {scheme_name}")
                print(f"ISIN: {isin}")
                
                # Look ahead for closing balance line
                for j in range(i+1, min(i+10, len(lines))):
                    if 'Closing Unit Balance:' in lines[j]:
                        # Extract units, nav, cost and value
                        balance_line = lines[j]
                        print(f"Balance line: {balance_line}")
                        
                        # Extract numbers from the line
                        numbers = re.findall(r'[\d,]+\.?\d*', balance_line)
                        if len(numbers) >= 3:
                            scheme.units = float(numbers[0].replace(',', ''))
                            scheme.nav = float(numbers[1].replace(',', ''))
                            scheme.value = float(numbers[2].replace(',', ''))
                            
                            # Calculate cost and gain
                            if cost_match := re.search(r'Cost:\s*Rs\.\s*([\d,]+\.?\d*)', balance_line):
                                scheme.cost = float(cost_match.group(1).replace(',', ''))
                                if scheme.cost > 0:
                                    scheme.gain.absolute = scheme.value - scheme.cost
                                    scheme.gain.percentage = (scheme.gain.absolute / scheme.cost) * 100
                            
                            print(f"Units: {scheme.units}")
                            print(f"NAV: {scheme.nav}")
                            print(f"Value: {scheme.value}")
                            
                            # Add scheme to the list
                            self.cas_data.schemes.append(scheme)
                            break
                
                # Look for transactions
                in_transactions = False
                for j in range(i+1, len(lines)):
                    line = lines[j].strip()
                    
                    # Stop if we hit the next scheme
                    if 'ISIN:' in line:
                        break
                    
                    # Look for transaction lines
                    if re.match(r'\d{2}-[A-Za-z]{3}-\d{4}', line):
                        # Parse transaction
                        parts = line.split()
                        if len(parts) >= 5:
                            date = datetime.strptime(parts[0], '%d-%b-%Y')
                            desc = ' '.join(parts[1:-3])
                            
                            try:
                                amount = float(parts[-3].replace(',', ''))
                                units = float(parts[-2].replace(',', ''))
                                nav = float(parts[-1].replace(',', ''))
                                
                                txn = Transaction(
                                    folio_number=current_folio,
                                    amc=current_amc,
                                    scheme_name=scheme_name,
                                    date=date,
                                    description=desc,
                                    amount=amount,
                                    units=units,
                                    nav=nav
                                )
                                
                                # Determine transaction type
                                if 'Purchase' in desc:
                                    txn.type = 'PURCHASE_SIP' if 'SIP' in desc else 'PURCHASE'
                                elif 'Redemption' in desc:
                                    txn.type = 'REDEMPTION'
                                elif 'Switch Out' in desc:
                                    txn.type = 'SWITCH_OUT'
                                elif 'Switch In' in desc:
                                    txn.type = 'SWITCH_IN'
                                elif 'Dividend' in desc:
                                    txn.type = 'DIVIDEND_PAYOUT' if 'Payout' in desc else 'DIVIDEND_REINVESTMENT'
                                    if dividend_match := re.search(r'@\s*Rs\.\s*([\d.]+)', desc):
                                        txn.dividend_rate = float(dividend_match.group(1))
                                else:
                                    txn.type = 'MISC'
                                
                                self.cas_data.transactions.append(txn)
                            except (ValueError, IndexError):
                                print(f"Failed to parse transaction: {line}")
                                continue

    def _calculate_portfolio_summary(self) -> None:
        """Calculate portfolio summary from extracted data"""
        # Initialize counters
        mf_count = len(self.cas_data.schemes)
        mf_value = sum(scheme.value for scheme in self.cas_data.schemes if scheme.value is not None)
        
        # Update portfolio summary
        self.cas_data.portfolio_summary.mutual_funds.count = float(mf_count)
        self.cas_data.portfolio_summary.mutual_funds.total_value = mf_value
        
        # Set total value (currently only mutual funds)
        self.cas_data.portfolio_summary.total_value = mf_value
        
        print(f"\nPortfolio Summary:")
        print(f"Mutual Funds: {mf_count} schemes, Total Value: Rs. {mf_value:,.2f}")
        print(f"Total Portfolio Value: Rs. {mf_value:,.2f}")

    def _extract_meta_info(self, text: str) -> Dict[str, Any]:
        """Extract meta information from text"""
        import re
        meta = {
            "cas_type": "CAMS",  # This is a CAMS CAS
            "generated_at": None,
            "statement_period": {
                "from": None,
                "to": None
            }
        }
        
        # Extract statement period from header
        period_pattern = r"Statement for the period from (\d{2}-[A-Za-z]{3}-\d{4}) to (\d{2}-[A-Za-z]{3}-\d{4})"
        if period_match := re.search(period_pattern, text):
            # Convert dates from DD-MMM-YYYY to YYYY-MM-DD
            from_date = datetime.strptime(period_match.group(1), "%d-%b-%Y").strftime("%Y-%m-%d")
            to_date = datetime.strptime(period_match.group(2), "%d-%b-%Y").strftime("%Y-%m-%d")
            meta["statement_period"]["from"] = from_date
            meta["statement_period"]["to"] = to_date
        
        # Extract generated_at from filename
        # Format: CAS_01012004-21062025_CP188509986_21062025053730617.pdf
        # Last part is YYYYMMDDHHmmSSsss
        generated_pattern = r"_(\d{14}\d*)\."
        if generated_match := re.search(generated_pattern, self.pdf_path):
            timestamp = generated_match.group(1)
            # Convert to ISO format
            year = timestamp[0:4]
            month = timestamp[4:6]
            day = timestamp[6:8]
            hour = timestamp[8:10]
            minute = timestamp[10:12]
            second = timestamp[12:14]
            meta["generated_at"] = f"{year}-{month}-{day}T{hour}:{minute}:{second}"
        
        return meta

    def extract_content(self) -> Dict[str, Any]:
        result = {
            "meta": {},
            "investor": {},
            "mutual_funds": [],
            "demat_accounts": []
        }
        
        try:
            # Open PDF file
            pdf = pdfplumber.open(self.pdf_path, password=self.password)
            
            # Initialize text
            all_text = ""
            
            # Iterate over pages
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    print(f"\nPage {page_num} content:")
                    print("-" * 20)
                    print(text)
                    print("-" * 20)
                    all_text += text + "\n"
            
            # Initialize lists for collecting data
            mutual_funds = []
            
            # Extract meta information
            result["meta"] = self._extract_meta_info(all_text)
            
            # Extract investor information
            result["investor"] = self._extract_investor_info(all_text)
            
            # Extract tables for mutual funds and demat holdings
            print("\nProcessing text for holdings...")
            for page in pdf.pages:
                text = page.extract_text()
                print(f"Processing page {page.page_number}")
                
                # Look for mutual fund sections
                if 'Mutual Fund Folios' in text:
                    print("\nFound mutual fund section:")
                    print("Raw text:")
                    print(text)
                    
                    # Extract mutual funds
                    funds = self._extract_mutual_funds(text)
                    mutual_funds.extend(funds)
                
                # Look for demat sections
                if 'Demat Holdings' in text:
                    print("Found demat section")
                    lines = text.split('\n')
                    in_table = False
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        # Look for the start of the table
                        if 'ISIN' in line and 'Security Name' in line:
                            in_table = True
                            continue
                            
                        if in_table:
                            # Skip header lines and totals
                            if any(x in line.lower() for x in ['total', 'isin', 'security name']):
                                continue
                                
                            # Try to parse holding details
                            parts = [p.strip() for p in line.split('  ') if p.strip()]
                            if len(parts) >= 4:
                                try:
                                    holding = {
                                        "isin": parts[0],
                                        "security_name": parts[1],
                                        "quantity": int(parts[-3].replace(',', '')) if len(parts) > 3 else 0,
                                        "current_price": float(parts[-2].replace(',', '')) if len(parts) > 2 else 0.0,
                                        "current_value": float(parts[-1].replace(',', '')) if len(parts) > 1 else 0.0
                                    }
                                    print(f"Found holding: {holding['security_name']}")
                                    result["demat_accounts"].append(holding)
                                except (ValueError, IndexError) as e:
                                    print(f"Error parsing holding line: {e}")
            
            # Assign collected mutual funds to result
            result["mutual_funds"] = mutual_funds
            
            return result
            
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            return {"error": str(e)}

    def save_to_json(self, output_path: str) -> None:
        """
        Save the extracted content to a JSON file
        """
        content = self.extract_content()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
