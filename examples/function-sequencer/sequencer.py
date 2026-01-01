from crossplane.pythonic import BaseComposite

class Composite(BaseComposite):
    def compose(self):
        for sequence in self.parameters:
            for ix, resource in enueration(sequence):
                if ix == 0:
                    continue
                if self.resources[resource].observed:
                    continue
                for before in sequence[:ix]:
                    
