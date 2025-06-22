import pdfplumber
import pandas as pd
from models import CASData, InvestorInfo, MutualFund, Meta, PortfolioSummary
import re
from datetime import datetime

class CASParser:
    def __init__(self, pdf_path, password):
        self.pdf_path = pdf_path
        self.password = password
        self.text = self._extract_text()
        self.cas_data = CASData()
        
    def _extract_text(self) -> str:
        """Extract text from PDF using password"""
        with pdfplumber.open(self.pdf_path, password=self.password) as pdf:
            return "\n".join(page.extract_text() for page in pdf.pages)
            
    def _extract_investor_info(self) -> None:
        """Extract investor information from CAS"""
        # Extract PAN
        pan_pattern = r"PAN:\s*([A-Z]{5}\d{4}[A-Z])"
        if pan_match := re.search(pan_pattern, self.text):
            self.cas_data.investor_info.pan = pan_match.group(1)
            
        # Extract name - look for lines with PAN
        name_pattern = r"^([^\n]+)\s+PAN:"
        if name_match := re.search(name_pattern, self.text, re.MULTILINE):
            self.cas_data.investor_info.name = name_match.group(1).strip()
            
        # Extract email and mobile
        email_pattern = r"Email ID:\s*([^\s]+@[^\s]+)"
        mobile_pattern = r"Mobile:\s*(\d{10})"
        
        if email_match := re.search(email_pattern, self.text):
            self.cas_data.investor_info.email = email_match.group(1)
            
        if mobile_match := re.search(mobile_pattern, self.text):
            self.cas_data.investor_info.mobile = mobile_match.group(1)
            
    def _extract_meta(self) -> None:
        """Extract CAS metadata"""
        # Statement period
        period_pattern = r"Statement Period:\s*([^\n]+)"
        if period_match := re.search(period_pattern, self.text):
            self.cas_data.meta.statement_period = period_match.group(1).strip()
            
        # CAS type
        if "DETAILED CONSOLIDATED ACCOUNT STATEMENT" in self.text:
            self.cas_data.meta.cas_type = "DETAILED"
        else:
            self.cas_data.meta.cas_type = "SUMMARY"
            
    def _extract_mutual_funds(self) -> None:
        """Extract mutual fund information"""
        # Split text into sections by folio
        folio_pattern = r"Folio No:\s*([^\n]+)"
        sections = re.split(folio_pattern, self.text)[1:]  # Skip header
        
        for i in range(0, len(sections), 2):
            if i + 1 >= len(sections):
                break
                
            folio = sections[i].strip()
            content = sections[i + 1]
            
            # Extract scheme details
            scheme_pattern = r"([^\n]+)\s+\(([A-Z0-9]+)\)"
            scheme_matches = re.finditer(scheme_pattern, content)
            
            for match in scheme_matches:
                scheme_name = match.group(1).strip()
                isin = match.group(2)
                
                # Create mutual fund object
                mf = MutualFund(
                    folio=folio,
                    scheme=scheme_name,
                    isin=isin
                )
                
                # Extract transactions
                trans_pattern = r"(\d{2}-[A-Za-z]{3}-\d{4})\s+([^\n]+)"
                trans_matches = re.finditer(trans_pattern, content)
                
                for trans in trans_matches:
                    date = trans.group(1)
                    details = trans.group(2).split()
                    
                    if len(details) >= 3:
                        try:
                            units = float(details[-2])
                            nav = float(details[-1])
                            
                            mf.transactions.append({
                                "date": date,
                                "type": details[0],
                                "units": units,
                                "nav": nav,
                                "amount": units * nav
                            })
                        except ValueError:
                            continue
                            
                self.cas_data.mutual_funds.append(mf)
                
    def _calculate_summary(self) -> None:
        """Calculate portfolio summary"""
        total_value = 0
        mf_count = len(self.cas_data.mutual_funds)
        
        for mf in self.cas_data.mutual_funds:
            # Calculate current value from latest transaction
            if mf.transactions:
                latest = mf.transactions[-1]
                mf.current_value = latest["units"] * latest["nav"]
                total_value += mf.current_value
                
        self.cas_data.portfolio_summary = PortfolioSummary(
            total_value=total_value,
            mutual_funds={
                "count": mf_count,
                "total_value": total_value
            }
        )
        
    def parse(self) -> CASData:
        """Parse CAS PDF and return structured data"""
        self._extract_meta()
        self._extract_investor_info()
        self._extract_mutual_funds()
        self._calculate_summary()
        return self.cas_data
        
    def to_excel(self, output_path: str) -> None:
        """Export CAS data to Excel"""
        # Create Excel writer
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Investor info sheet
            pd.DataFrame([{
                "Name": self.cas_data.investor_info.name,
                "PAN": self.cas_data.investor_info.pan,
                "Email": self.cas_data.investor_info.email,
                "Mobile": self.cas_data.investor_info.mobile
            }]).to_excel(writer, sheet_name="Investor Info", index=False)
            
            # Portfolio summary sheet
            pd.DataFrame([{
                "Total Value": self.cas_data.portfolio_summary.total_value,
                "Number of Mutual Funds": self.cas_data.portfolio_summary.mutual_funds["count"]
            }]).to_excel(writer, sheet_name="Portfolio Summary", index=False)
            
            # Mutual funds sheet
            mf_data = []
            for mf in self.cas_data.mutual_funds:
                for trans in mf.transactions:
                    mf_data.append({
                        "Folio": mf.folio,
                        "Scheme": mf.scheme,
                        "ISIN": mf.isin,
                        "Date": trans["date"],
                        "Type": trans["type"],
                        "Units": trans["units"],
                        "NAV": trans["nav"],
                        "Amount": trans["amount"]
                    })
                    
            if mf_data:
                pd.DataFrame(mf_data).to_excel(writer, sheet_name="Mutual Funds", index=False)
